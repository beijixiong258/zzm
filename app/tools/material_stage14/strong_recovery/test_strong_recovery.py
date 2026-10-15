"""Focused offline + protocol tests. Any HTTP server here is a protocol fixture.

Run from app root with -B; no real model, OCR inference, GPU, deployment, or lease.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import itertools
import json
from pathlib import Path
import threading
import unittest

from tools.material_stage14.strong_recovery.alignment import (
    align_evidence, normalized, ordered_alignment, parse_lines)
from tools.material_stage14.strong_recovery.offline import (
    DEFAULT_INPUTS, DEFAULT_OUTPUT, archived_generation, digest, load_json,
    verify_spatial, write_json)
from tools.material_stage14.strong_recovery.protocol import (
    HTTPReply, LoopbackLineClient, SOURCE_FAITHFUL_PROMPT, sha256)


def detection(text, score=0.99, x=0.1, y=0.1):
    box = [x, y, x + 0.1, y + 0.02]
    return {"text": text, "confidence": score, "bbox": box,
            "polygon": [[box[0], box[1]], [box[2], box[1]],
                        [box[2], box[3]], [box[0], box[3]]]}


def fixture_inputs(vlm, cpu, uncertainties=None):
    scan = {"engine": "rapidocr-onnx-cpu", "available": True,
            "actual_providers": ["CPUExecutionProvider"], "status": "complete",
            "input_size": [100, 200], "input_pixel_sha256": "fixture-pixels",
            "lines": [detection(t, y=0.05 + i * 0.04) for i, t in enumerate(cpu)]}
    generation = {"content": json.dumps({"lines": vlm, "uncertainties": uncertainties or []}),
                  "finish_reason": "stop", "usage": {"completion_tokens": 10},
                  "finish_provenance": "openai_compatible_response_choice",
                  "protocol_errors": [], "input_image_sha256": "fixture-image"}
    spatial = {"input_binding_verified": True, "input_sha256": "fixture-image",
               "input_size": [100, 200], "input_pixel_sha256": "fixture-pixels",
               "crop_to_raster_verified": False,
               "spatial_parent": {"kind": "protocol_fixture_no_gpu"}}
    return scan, generation, spatial


def propose(vlm, cpu, **kwargs):
    return align_evidence(*fixture_inputs(vlm, cpu), evidence_kind="synthetic_unit_fixture_no_gpu", **kwargs)


class AlignmentTests(unittest.TestCase):
    def test_nfc_layout_whitespace_only(self):
        result = propose(["Cafe\u0301  test\tABC"], ["Café test ABC"])
        self.assertEqual(result["counts"]["text_candidates"], 1)
        self.assertEqual(result["text_candidates"][0]["raw_text"], "Cafe\u0301  test\tABC")

    def test_case_punctuation_digits_glyphs_and_source_name_not_corrected(self):
        pairs = [("Margoargo", "Margorgo"), ("Margoargo", "Margo"),
                 ("ABC", "abc"), ("a,b", "a b"), ("O0", "00"),
                 ("1.5", "15"), ("• text", "text"), ("page 110", "page110"),
                 ("inter-", "inter"), ("’", "'"), ("①", "1")]
        for vlm, cpu in pairs:
            with self.subTest(vlm=vlm, cpu=cpu):
                result = propose([vlm], [cpu])
                self.assertEqual(result["counts"]["text_candidates"], 0)
                self.assertEqual(result["counts"]["unmatched_cpu_detections"], 1)
                self.assertEqual(result["raw_cpu_scan"]["lines"][0]["text"], cpu)
                self.assertEqual(result["vlm_records"][0]["raw_text"], vlm)

    def test_adjacent_header_detections_merge_preserving_order(self):
        result = propose(["118 CHAPTER 5", "body"], ["118", "CHAPTER 5", "body"])
        self.assertEqual([p["cpu_indices"] for p in result["text_candidates"]], [[0, 1], [2]])

    def test_non_contiguous_and_reversed_groups_not_merged(self):
        for vlm, cpu in [(["A B"], ["A", "X", "B"]), (["A B"], ["B", "A"])]:
            with self.subTest(cpu=cpu):
                self.assertEqual(propose(vlm, cpu)["counts"]["text_candidates"], 0)

    def test_global_order_not_greedy(self):
        result = propose(["B", "A"], ["A", "B", "A"])
        self.assertEqual([p["cpu_indices"] for p in result["text_candidates"]], [[1], [2]])
        self.assertEqual(result["cpu_records"][0]["alignment_state"], "unmatched")

    def test_duplicate_cpu_occurrences_ambiguous_not_chosen(self):
        result = propose(["same"], ["same", "same"])
        row = result["vlm_records"][0]
        self.assertEqual(row["optimal_cpu_group_alternatives"], [[0], [1]])
        self.assertFalse(row["candidate_eligible"])
        self.assertEqual(result["counts"]["text_candidates"], 0)
        self.assertEqual([r["alignment_state"] for r in result["cpu_records"]],
                         ["ambiguous_exact", "ambiguous_exact"])

    def test_duplicate_model_occurrences_ambiguous_not_fabricated(self):
        result = propose(["same", "same"], ["same"])
        self.assertEqual(result["counts"]["text_candidates"], 0)
        self.assertTrue(all(r["can_be_unmatched_in_optimum"] for r in result["vlm_records"]))

    def test_duplicate_lines_uniquely_ordered_can_match(self):
        result = propose(["same", "same"], ["same", "same"])
        self.assertEqual([p["cpu_indices"] for p in result["text_candidates"]], [[0], [1]])

    def test_crossed_order_is_withheld_not_arbitrarily_tie_broken(self):
        result = propose(["A", "B"], ["B", "A"])
        self.assertEqual(result["counts"]["optimal_exact_groups"], 1)
        self.assertEqual(result["counts"]["text_candidates"], 0)

    def test_missing_cpu_and_extra_model_all_retained(self):
        result = propose(["A", "model extra", "C"], ["A", "CPU missed by model", "C"])
        self.assertEqual(result["counts"]["text_candidates"], 2)
        self.assertEqual(result["vlm_records"][1]["raw_text"], "model extra")
        self.assertEqual(result["cpu_records"][1]["raw_detection"]["text"], "CPU missed by model")
        self.assertEqual(result["cpu_records"][1]["alignment_state"], "unmatched")

    def test_low_confidence_is_aligned_but_not_candidate(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        for score in [0.939999, 0, -1, 1.01, float("nan"), float("inf"), "0.99", True, None]:
            with self.subTest(score=repr(score)):
                scan["lines"][0]["confidence"] = score
                result = align_evidence(scan, generation, spatial)
                self.assertEqual(result["counts"]["unique_exact_groups"], 1)
                self.assertEqual(result["counts"]["text_candidates"], 0)
                self.assertTrue(result["cpu_records"][0]["review_reasons"])
        scan["lines"][0]["confidence"] = 0.94
        self.assertEqual(align_evidence(scan, generation, spatial)["counts"]["text_candidates"], 1)

    def test_all_non_stop_finishes_block_even_valid_json(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        for finish in [None, "length", "content_filter", "tool_calls", "unknown", "eos", ""]:
            with self.subTest(finish=finish):
                generation["finish_reason"] = finish
                result = align_evidence(scan, generation, spatial)
                self.assertEqual(result["counts"]["text_candidates"], 0)
                self.assertEqual(result["raw_generation"]["finish_reason"], finish)
                self.assertEqual(result["counts"]["unique_exact_groups"], 1)

    def test_content_cannot_self_assert_actual_finish(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        generation["finish_provenance"] = "model_claim"
        self.assertEqual(align_evidence(scan, generation, spatial)["counts"]["text_candidates"], 0)
        generation["finish_provenance"] = "openai_compatible_response_choice"
        generation["protocol_errors"] = ["http_status_not_200"]
        self.assertEqual(align_evidence(scan, generation, spatial)["counts"]["text_candidates"], 0)

    def test_model_uncertainty_not_lost_and_empty_not_authority(self):
        scan, generation, spatial = fixture_inputs(["A", "B"], ["A", "B"],
                                                   [{"line_index": 1, "reason": "faint"}])
        result = align_evidence(scan, generation, spatial)
        self.assertEqual([p["vlm_line_index"] for p in result["text_candidates"]], [0])
        self.assertEqual(result["decoded_model_payload"]["uncertainties"][0]["reason"], "faint")
        generation["content"] = json.dumps({"lines": ["wrong", "B"], "uncertainties": []})
        result = align_evidence(scan, generation, spatial)
        self.assertEqual([p["vlm_line_index"] for p in result["text_candidates"]], [1])

    def test_missing_unscoped_or_malformed_uncertainty_withholds(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        payloads = [{"lines": ["A"]}, {"lines": ["A"], "uncertainties": None},
                    {"lines": ["A"], "uncertainties": [{"line_index": None, "reason": "global"}]},
                    {"lines": ["A"], "uncertainties": ["faint"]},
                    {"lines": ["A"], "uncertainties": [{"line_index": 100, "reason": "invalid index"}]}]
        for payload in payloads:
            with self.subTest(payload=payload):
                generation["content"] = json.dumps(payload)
                self.assertEqual(align_evidence(scan, generation, spatial)["counts"]["text_candidates"], 0)

    def test_malformed_truncated_content_preserved_not_repaired(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        for content in ['{"lines":["A"', '```json\n{"lines":["A"],"uncertainties":[]}\n``` explanation',
                        '{"lines":[1],"uncertainties":[]}', '["A"]', 'not json']:
            with self.subTest(content=content):
                generation["content"] = content
                result = align_evidence(scan, generation, spatial)
                self.assertEqual(result["counts"]["text_candidates"], 0)
                self.assertEqual(result["raw_generation"]["content"], content)
                self.assertEqual(result["counts"]["cpu_detections"], 1)

    def test_cpu_independence_and_input_binding_required(self):
        mutations = [("cpu", "engine", "same-vlm"), ("cpu", "actual_providers", ["CUDAExecutionProvider"]),
                     ("cpu", "status", "unavailable"), ("cpu", "available", False),
                     ("cpu", "input_pixel_sha256", "wrong"), ("cpu", "input_size", [1, 2]),
                     ("spatial", "input_binding_verified", False), ("generation", "input_image_sha256", "wrong")]
        for target, key, value in mutations:
            with self.subTest(target=target, key=key):
                scan, generation, spatial = fixture_inputs(["A"], ["A"])
                {"cpu": scan, "generation": generation, "spatial": spatial}[target][key] = value
                self.assertEqual(align_evidence(scan, generation, spatial)["counts"]["text_candidates"], 0)

    def test_invalid_bbox_or_polygon_never_invented(self):
        for key, value in [("bbox", None), ("polygon", []), ("bbox", [0, 0, 0, 0]),
                           ("bbox", [0, 0, 2, 1]), ("polygon", [[0, float("nan")]]),
                           ("bbox", [0.2, 0.2, 0.8, 0.8])]:
            with self.subTest(key=key, value=repr(value)):
                scan, generation, spatial = fixture_inputs(["A"], ["A"])
                scan["lines"][0][key] = value
                result = align_evidence(scan, generation, spatial)
                self.assertEqual(result["counts"]["text_candidates"], 0)
                self.assertEqual(result["vlm_records"][0]["location"]["source_raster_mapping_status"], "unproven")

    def test_unproven_crop_keeps_parent_only_no_raster_or_page_bbox(self):
        result = propose(["A"], ["A"])
        self.assertEqual(result["counts"]["text_candidates"], 1)
        location = result["text_candidates"][0]["location"]
        self.assertEqual(location["page_location_status"], "spatial-parent-only")
        self.assertNotIn("source_raster_group_bbox_pixels", location)
        self.assertNotIn("page_bbox", location)

    def test_table_diagram_literal_only_and_inputs_not_mutated(self):
        scan, generation, spatial = fixture_inputs(["A"], ["A"])
        before = deepcopy((scan, generation, spatial))
        for kind in ["table", "diagram", "figure", "unknown", "prose"]:
            with self.subTest(kind=kind):
                result = align_evidence(scan, generation, spatial, region_kind=kind)
                self.assertEqual(result["structure_status"], "unverified")
                self.assertEqual(result["semantic_status"], "not_evaluated")
                self.assertFalse(result["whole_source_accepted"])
                self.assertEqual(result["text_candidates"][0]["state"], "candidate_only")
                self.assertEqual(result["text_candidates"][0]["structure_status"], "unverified")
        self.assertEqual((scan, generation, spatial), before)

    def test_dp_against_exhaustive_optimum_oracle_for_repeats_and_merges(self):
        # Independent exhaustive match-set oracle (not a second greedy alignment).
        # Small finite cases verify all-optimum ambiguity, not just one traceback.
        sequences = [()] + [s for k in range(1, 4) for s in itertools.product(("A", "B"), repeat=k)]
        checks = 0
        for v in sequences + [("A B",), ("A", "A B"), ("A B", "B")]:
            for c in sequences:
                @lru_cache(None)
                def paths(i, j):
                    if i == len(v) or j == len(c):
                        return frozenset({()})
                    answers = set(paths(i + 1, j)) | set(paths(i, j + 1))
                    for k in range(1, min(2, len(c) - j) + 1):
                        if normalized(v[i]) == normalized(" ".join(c[j:j + k])):
                            answers.update(((i, tuple(range(j, j + k))),) + tail for tail in paths(i + 1, j + k))
                    return frozenset(answers)
                all_paths = paths(0, 0)
                best_size = max(map(len, all_paths))
                best = [p for p in all_paths if len(p) == best_size]
                result = ordered_alignment(list(v), [detection(t) for t in c])
                self.assertEqual(result["optimal_exact_group_count"], best_size, (v, c))
                for record in result["vlm"]:
                    i = record["vlm_line_index"]
                    options = {group for p in best for index, group in p if index == i}
                    can_skip = any(not any(index == i for index, _ in p) for p in best)
                    expected_state = "unique_exact" if len(options) == 1 and not can_skip else "ambiguous_exact" if options else "unmatched"
                    self.assertEqual(record["alignment_state"], expected_state, (v, c, i))
                    self.assertEqual({tuple(g) for g in record["optimal_cpu_group_alternatives"]}, options)
                checks += 1
        self.assertEqual(checks, 270)


class RealInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = load_json(DEFAULT_INPUTS / "vision-lines-r3-result.json")
        cls.cpu = load_json(DEFAULT_INPUTS / "cpu-columns.json")
        cls.transforms = load_json(DEFAULT_INPUTS / "transforms.json")
        cls.baseline = load_json(DEFAULT_INPUTS / "line-alignment.json")

    def test_real_cases_exact_counts_and_same_occurrences(self):
        expected = {"p1-left-page-2x.png": (24, 25, 23, 1, 1),
                    "p9-left-page-2x.png": (39, 40, 34, 5, 5)}
        for t in self.transforms:
            with self.subTest(image=t["output"]):
                name = t["output"]
                case = next(c for c in self.vision["cases"] if c["name"] == name)
                spatial = verify_spatial(DEFAULT_INPUTS, t, self.cpu[name], case)
                result = align_evidence(self.cpu[name], archived_generation(case), spatial)
                counts = result["counts"]
                self.assertEqual(tuple(counts[k] for k in ("vlm_lines", "cpu_detections", "text_candidates",
                                                          "unmatched_vlm_lines", "unmatched_cpu_detections")), expected[name])
                baseline = next(c for c in self.baseline["cases"] if c["image"] == name)
                self.assertEqual([(p["vlm_line_index"], p["cpu_indices"]) for p in result["text_candidates"]],
                                 [(p["vlm_line_index"], p["cpu_indices"]) for p in baseline["matches"]])
                self.assertTrue(spatial["input_binding_verified"])
                self.assertTrue(spatial["crop_to_raster_verified"])
                self.assertEqual(result["raw_generation"]["raw_archived_case"], case)
                self.assertEqual(result["raw_cpu_scan"], self.cpu[name])

    def test_real_name_error_preserved_despite_empty_model_uncertainties(self):
        t = self.transforms[0]
        case = self.vision["cases"][0]
        scan = self.cpu[t["output"]]
        result = align_evidence(scan, archived_generation(case), verify_spatial(DEFAULT_INPUTS, t, scan, case))
        self.assertEqual(result["decoded_model_payload"]["uncertainties"], [])
        self.assertIn("Margorgo", result["vlm_records"][15]["raw_text"])
        self.assertFalse(result["vlm_records"][15]["candidate_eligible"])
        self.assertIn("Margoargo", result["cpu_records"][16]["raw_detection"]["text"])
        self.assertEqual(result["cpu_records"][16]["alignment_state"], "unmatched")
        self.assertFalse(any("Margorgo" in p["raw_text"] or "Margoargo" in p["raw_text"] for p in result["text_candidates"]))

    def test_real_p9_garbled_lowconfidence_and_bullet_disagreements_retained(self):
        t = self.transforms[1]
        case = self.vision["cases"][1]
        scan = self.cpu[t["output"]]
        result = align_evidence(scan, archived_generation(case), verify_spatial(DEFAULT_INPUTS, t, scan, case))
        self.assertEqual([r["cpu_index"] for r in result["cpu_records"] if r["alignment_state"] == "unmatched"],
                         [17, 19, 20, 34, 39])
        self.assertEqual(result["counts"]["low_confidence_cpu_detections"], 2)
        self.assertEqual(scan["lines"][17]["confidence"], 0.65402)
        self.assertEqual(scan["lines"][19]["confidence"], 0.63975)
        self.assertIn("•", result["vlm_records"][33]["raw_text"])
        self.assertNotIn("•", result["cpu_records"][34]["raw_detection"]["text"])

    def test_real_raster_mapping_not_document_page_placement(self):
        t = self.transforms[0]
        scan = self.cpu[t["output"]]
        case = self.vision["cases"][0]
        spatial = verify_spatial(DEFAULT_INPUTS, t, scan, case)
        result = align_evidence(scan, archived_generation(case), spatial)
        p = result["text_candidates"][1]
        original = scan["lines"][p["cpu_indices"][0]]["polygon"][0]
        mapped = p["location"]["source_raster_geometry"][0]["polygon_pixels"][0]
        self.assertAlmostEqual(mapped[0], 144 + original[0] * 1816 / 2)
        self.assertAlmostEqual(mapped[1], 58 + original[1] * 2564 / 2)
        self.assertEqual(p["location"]["page_location_status"], "spatial-parent-only")
        self.assertIsNone(spatial["raster_to_document_page_transform"])
        self.assertNotIn("page_bbox", p["location"])

    def test_bad_transform_not_used_but_valid_input_binding_can_remain(self):
        t = deepcopy(self.transforms[0])
        t["scale"] = 1
        scan = self.cpu[t["output"]]
        case = self.vision["cases"][0]
        spatial = verify_spatial(DEFAULT_INPUTS, t, scan, case)
        self.assertTrue(spatial["input_binding_verified"])
        self.assertFalse(spatial["crop_to_raster_verified"])
        result = align_evidence(scan, archived_generation(case), spatial)
        self.assertEqual(result["counts"]["text_candidates"], 23)
        self.assertNotIn("source_raster_group_bbox_pixels", result["text_candidates"][0]["location"])
        t["sha256"] = "wrong"
        spatial = verify_spatial(DEFAULT_INPUTS, t, scan, case)
        self.assertFalse(spatial["input_binding_verified"])
        self.assertEqual(align_evidence(scan, archived_generation(case), spatial)["counts"]["text_candidates"], 0)

    def test_real_non_stop_metadata_has_no_retrospective_candidates(self):
        t = self.transforms[0]
        scan = self.cpu[t["output"]]
        case = self.vision["cases"][0]
        spatial = verify_spatial(DEFAULT_INPUTS, t, scan, case)
        generation = archived_generation(case)
        generation["finish_reason"] = "length"
        result = align_evidence(scan, generation, spatial)
        self.assertEqual(result["counts"]["unique_exact_groups"], 23)
        self.assertEqual(result["counts"]["text_candidates"], 0)
        self.assertEqual(result["raw_generation"]["raw_archived_case"], case)


class ProtocolTests(unittest.TestCase):
    def test_nonloopback_hostname_credentials_paths_rejected_before_transport(self):
        invalid = ["http://192.168.32.1:8000", "https://127.0.0.1:8000", "http://localhost:8000",
                   "http://127.0.0.1", "http://user:pw@127.0.0.1:8000", "http://127.0.0.1:8000/other",
                   "http://127.0.0.1:8000/v1?x=1", "http://127.0.0.1:8000/#x"]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                LoopbackLineClient(url, "fixture")
        self.assertEqual(LoopbackLineClient("http://[::1]:8000/v1", "fixture").endpoint,
                         "http://[::1]:8000/v1/chat/completions")

    def test_injected_transport_preserves_raw_response_finish_usage_and_fixed_prompt(self):
        raw = b'{ "choices": [{"message":{"content":"{\\"lines\\":[\\"A\\"],\\"uncertainties\\":[]}"},"finish_reason":"length"}], "usage":{"completion_tokens":42}, "unknown": "kept" }\n'
        captured = []
        def transport(url, body, timeout):
            captured.append((url, body, timeout))
            return HTTPReply(200, (("Content-Type", "application/json"),), raw)
        record = LoopbackLineClient("http://127.0.0.1:9/v1", "fixture", transport=transport).transcribe(
            b"explicit-image-protocol-fixture", evidence_kind="injected_protocol_fixture_no_gpu")
        self.assertEqual(base64.b64decode(record["response"]["body_base64"]), raw)
        self.assertEqual(record["response"]["body_sha256"], sha256(raw))
        self.assertEqual(record["generation"]["finish_reason"], "length")
        self.assertEqual(record["generation"]["usage"], {"completion_tokens": 42})
        self.assertEqual(record["response"]["parsed"]["unknown"], "kept")
        request = json.loads(captured[0][1])
        self.assertEqual(request["messages"][0]["content"], SOURCE_FAITHFUL_PROMPT)
        self.assertEqual(request["temperature"], 0)
        self.assertFalse(request["stream"])
        self.assertFalse(request["cache_prompt"])
        self.assertTrue(record["transport_injected"])
        self.assertFalse(record["gpu_acceptance"])

    def test_response_errors_retained_and_never_eligible(self):
        bodies = [(500, b'{"error":"fixture failure"}'), (200, b'not-json'),
                  (200, b'{"choices":[]}'), (200, b'{"choices":[{},{}]}'),
                  (200, b'{"choices":[{"finish_reason":"stop","message":{"content":null}}]}'),
                  (302, b'fixture redirect must not be followed')]
        for status, raw in bodies:
            with self.subTest(status=status, raw=raw):
                record = LoopbackLineClient("http://127.0.0.1:9", "fixture",
                    transport=lambda *args: HTTPReply(status, (), raw)).transcribe(b"fixture")
                self.assertTrue(record["generation"]["protocol_errors"])
                self.assertEqual(base64.b64decode(record["response"]["body_base64"]), raw)
                self.assertEqual(record["response"]["status"], status)

    def test_transport_failure_preserves_request_without_fabricating_response(self):
        def unavailable(*args):
            raise ConnectionRefusedError("explicit fixture refusal")
        record = LoopbackLineClient("http://127.0.0.1:9", "fixture", transport=unavailable).transcribe(b"fixture")
        self.assertIsNone(record["response"])
        self.assertEqual(record["generation"]["protocol_errors"], ["transport_failure"])
        self.assertEqual(record["transport_error"]["type"], "ConnectionRefusedError")
        self.assertEqual(record["request"]["body_sha256"], sha256(base64.b64decode(record["request"]["body_base64"])))

    def test_missing_transport_finish_not_filled_from_model_claim(self):
        content = json.dumps({"lines": ["A"], "uncertainties": [], "finish_reason": "stop"})
        raw = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        record = LoopbackLineClient("http://127.0.0.1:9", "fixture",
                    transport=lambda *args: HTTPReply(200, (), raw)).transcribe(b"fixture")
        self.assertIsNone(record["generation"]["finish_reason"])
        self.assertIn("finish_reason", record["generation"]["content"])
        scan, _, spatial = fixture_inputs(["A"], ["A"])
        spatial["input_sha256"] = sha256(b"fixture")
        self.assertEqual(align_evidence(scan, record["generation"], spatial)["counts"]["text_candidates"], 0)

    def test_real_http_loopback_is_protocol_fixture_only(self):
        from PIL import Image
        image_buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_buffer, format="PNG")
        image = image_buffer.getvalue()
        fixture_payload = {"id": "protocol-fixture-not-gpu", "model": "protocol-fixture-not-gpu",
                           "choices": [{"index": 0, "message": {"role": "assistant", "content":
                                       json.dumps({"lines": ["FIXTURE ONLY"], "uncertainties": []})},
                                        "finish_reason": "stop"}], "usage": {"completion_tokens": 8}}
        response_body = json.dumps(fixture_payload).encode()
        seen = []
        class FixtureHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                seen.append({"path": self.path, "body_sha256": sha256(body), "request": json.loads(body)})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            record = LoopbackLineClient(f"http://127.0.0.1:{server.server_port}/v1", "protocol-fixture-not-gpu",
                                       timeout=10).transcribe(image, evidence_kind="actual_http_protocol_fixture_no_gpu")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["path"], "/v1/chat/completions")
        self.assertEqual(record["request"]["body_sha256"], seen[0]["body_sha256"])
        self.assertEqual(record["generation"]["finish_reason"], "stop")
        self.assertEqual(record["generation"]["protocol_errors"], [])
        self.assertEqual(base64.b64decode(record["response"]["body_base64"]), response_body)
        self.assertFalse(record["gpu_acceptance"])
        write_json(DEFAULT_OUTPUT / "protocol-http-fixture-receipt.json",
                   {"execution": "actual_loopback_http_protocol_fixture_only", "gpu_acceptance": False,
                    "network_destination": "numeric_loopback_ephemeral_fixture", "server_closed": not thread.is_alive(),
                    "server_observation": seen, "client_capture": record})


if __name__ == "__main__":
    unittest.main(verbosity=2)
