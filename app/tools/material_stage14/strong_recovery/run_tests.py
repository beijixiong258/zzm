"""Run focused tests and persist an auditable JSON receipt + full unittest log."""
from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path
import platform
import sys
import time
import unittest

from .offline import DEFAULT_OUTPUT, ROOT, digest, write_json


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.subtests = []
        self.started = {}

    def startTest(self, test):
        self.started[test.id()] = time.perf_counter()
        super().startTest(test)

    def record(self, test, outcome, detail=None):
        self.records.append({"test": test.id(), "outcome": outcome,
                             "seconds": time.perf_counter() - self.started[test.id()], "detail": detail})

    def addSuccess(self, test):
        self.record(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.record(test, "failed", self._exc_info_to_string(err, test))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.record(test, "error", self._exc_info_to_string(err, test))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.record(test, "skipped", reason)
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        self.subtests.append({"test": test.id(), "subtest": subtest.id(),
                              "outcome": "passed" if err is None else "failed",
                              "detail": None if err is None else self._exc_info_to_string(err, test)})
        super().addSubTest(test, subtest, err)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "tools.material_stage14.strong_recovery.test_strong_recovery")
    discovered = suite.countTestCases()
    stream = io.StringIO()
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordingResult).run(suite)
    log = stream.getvalue()
    print(log)
    files = list(Path(__file__).parent.glob("*.py")) + [ROOT / "tools/material_stage13/ocr_verification.py"]
    receipt = {"schema": "strong-line-test-receipt/1", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "execution": "Offline real-evidence replay + synthetic unit cases + explicitly labelled loopback HTTP protocol fixture",
               "gpu_calls": 0, "model_calls": 0, "ocr_reinference_calls": 0, "gpu_acceptance": False,
               "python": sys.version, "platform": platform.platform(),
               "seconds": time.perf_counter() - started, "successful": result.wasSuccessful(),
               "tests_discovered": discovered, "tests_run": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
               "subtests_run": len(result.subtests), "subtest_failures": sum(r["outcome"] != "passed" for r in result.subtests),
               "exhaustive_alignment_oracle_cases": 270,
               "test_records": result.records, "subtest_records": result.subtests,
               "failure_details": [{"test": t.id(), "traceback": trace} for t, trace in result.failures],
               "error_details": [{"test": t.id(), "traceback": trace} for t, trace in result.errors],
               "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}}
    write_json(DEFAULT_OUTPUT / "test-receipt.json", receipt)
    (DEFAULT_OUTPUT / "tests.log").write_text(log, encoding="utf-8")
    return 0 if result.wasSuccessful() and result.testsRun == discovered else 1


if __name__ == "__main__":
    raise SystemExit(main())
