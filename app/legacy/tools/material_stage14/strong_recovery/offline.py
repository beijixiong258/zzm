"""Read-only replay of retained real CPU/27B inputs; write only own sidecars.

Run: .venv/Scripts/python.exe -B -m tools.material_stage14.strong_recovery.offline
No GPU/model/HTTP calls, no OCR re-inference, no worker or manifest modifications.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .alignment import align_evidence

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUTS = ROOT / "artifacts/stage14/ocr-line-calibration"
DEFAULT_OUTPUT = ROOT / "artifacts/stage14/strong-recovery"
RETAINED_JSON = ("vision-lines-r3-result.json", "cpu-columns.json", "transforms.json",
                 "line-alignment.json", "source-name-disagreement.json")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_json(path: Path):
    return json.loads(path.read_bytes().decode("utf-8"))


def pixel_digest(image) -> str:
    return hashlib.sha256(image.convert("RGB").tobytes() + str(image.size).encode()).hexdigest()


def verify_spatial(inputs: Path, transform: dict, cpu_scan: dict, case: dict) -> dict:
    """Verify image binding and crop->raster mapping by exact RGB reconstruction.

    File hashes, CPUVerifier RGB+size hash, dimensions, and LANCZOS reproduction
    must agree. This proves source-raster pixels only, NOT raster->PDF page space.
    """
    from PIL import Image
    source = inputs / transform["source"]
    crop = inputs / transform["output"]
    with Image.open(source) as source_file, Image.open(crop) as crop_file:
        src = source_file.convert("RGB")
        image = crop_file.convert("RGB")
        source_hash = digest(source)
        crop_hash = digest(crop)
        actual_pixels = pixel_digest(image)
        binding = (crop_hash == transform.get("sha256") == case.get("sha256")
                   and list(image.size) == cpu_scan.get("input_size")
                   and actual_pixels == cpu_scan.get("input_pixel_sha256"))
        rect = transform["crop"]
        scale = transform["scale"]
        valid_rect = (len(rect) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in rect)
                      and 0 <= rect[0] < rect[2] <= src.width and 0 <= rect[1] < rect[3] <= src.height)
        valid_scale = (isinstance(scale, (int, float)) and not isinstance(scale, bool) and scale > 0)
        dimensions = (valid_rect and valid_scale
                      and image.size == ((rect[2] - rect[0]) * scale, (rect[3] - rect[1]) * scale))
        recreated = bool(dimensions and src.crop(rect).resize(image.size, Image.Resampling.LANCZOS).tobytes()
                         == image.tobytes())
        mapping = (binding and source_hash == transform.get("source_sha256") and recreated)
        return {"spatial_parent": {"kind": "retained_source_raster", "file": str(source.resolve()),
                                   "sha256": source_hash},
                "source_raster": {"file": str(source.resolve()), "sha256": source_hash,
                                  "size_pixels": list(src.size)},
                "model_cpu_input": {"file": str(crop.resolve()), "sha256": crop_hash},
                "input_sha256": crop_hash, "input_size": list(image.size),
                "input_pixel_sha256": actual_pixels, "input_binding_verified": binding,
                "crop_pixels": deepcopy(rect), "scale": scale,
                "crop_to_raster_verified": bool(mapping),
                "transform_evidence": {"method": "Exact RGB source crop + Pillow LANCZOS scale reconstruction",
                                       "raw_record": deepcopy(transform), "file_hashes_match":
                                       source_hash == transform.get("source_sha256") and crop_hash == transform.get("sha256"),
                                       "dimensions_match": bool(dimensions), "recreated_pixels_match": recreated},
                "coordinate_equation": "source_raster_x = crop_left + input_normalized_x * input_width / scale; source_raster_y = crop_top + input_normalized_y * input_height / scale",
                "raster_to_document_page_transform": None,
                "page_location_status": "spatial-parent-only",
                "page_location_reason": "Retained crop record has no verified raster placement in document page coordinates; filename is not placement proof."}


def archived_generation(case: dict) -> dict:
    return {"content": case.get("content"), "finish_reason": case.get("finish_reason"),
            "usage": deepcopy(case.get("usage")), "input_image_sha256": case.get("sha256"),
            "finish_provenance": "archived_real_probe_case", "protocol_errors": [],
            "raw_archived_case": deepcopy(case), "raw_wire_http_response_available": False}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(inputs: Path = DEFAULT_INPUTS, output: Path = DEFAULT_OUTPUT) -> dict:
    # Limit the CLI writer to its explicitly delegated artifact tree.
    output = output.resolve()
    if not output.is_relative_to(DEFAULT_OUTPUT.resolve()):
        raise ValueError("Output must be inside artifacts/stage14/strong-recovery")
    transforms = load_json(inputs / "transforms.json")
    cpu = load_json(inputs / "cpu-columns.json")
    vision = load_json(inputs / "vision-lines-r3-result.json")
    baseline = load_json(inputs / "line-alignment.json")
    by_name = {case["name"]: case for case in vision["cases"]}
    if len(by_name) != len(vision["cases"]) or set(by_name) != set(cpu):
        raise ValueError("Each retained model case must have exactly one same-image CPU record")
    if {t["output"] for t in transforms} != set(by_name) or len(transforms) != len(by_name):
        raise ValueError("Exactly one retained transform per real input is required")
    paths = [inputs / name for name in RETAINED_JSON]
    paths += [inputs / t[key] for t in transforms for key in ("source", "output")]
    paths.append(ROOT / "tools/material_stage13/ocr_verification.py")
    before = {str(p.resolve()): digest(p) for p in paths}
    for name in RETAINED_JSON:
        target = output / "retained-inputs" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((inputs / name).read_bytes())
    cases = []
    for transform in transforms:
        name = transform["output"]
        case = by_name[name]
        scan = cpu[name]
        spatial = verify_spatial(inputs, transform, scan, case)
        proposal = align_evidence(scan, archived_generation(case), spatial,
                                  evidence_kind="offline_replay_of_retained_real_27B_and_cpu",
                                  region_kind="prose_crop_with_headers_and_bullets")
        proposal["source_capture"] = {"archived_case_name": name,
                                      "raw_wire_http_response_available": False,
                                      "retained_vision_result_sha256": digest(inputs / RETAINED_JSON[0]),
                                      "retained_cpu_result_sha256": digest(inputs / RETAINED_JSON[1]),
                                      "uncertainties_are_model_claims_only": True}
        sidecar_name = name.removesuffix(".png") + ".proposal.json"
        write_json(output / sidecar_name, proposal)
        raw_content_path = output / "raw-content" / (name + ".content.utf8")
        raw_content_path.parent.mkdir(parents=True, exist_ok=True)
        raw_content_path.write_bytes(case["content"].encode("utf-8"))
        baseline_case = next(c for c in baseline["cases"] if c["image"] == name)
        baseline_matches = [(c["vlm_line_index"], c["cpu_indices"]) for c in baseline_case["matches"]]
        matches = [(c["vlm_line_index"], c["cpu_indices"]) for c in proposal["text_candidates"]]
        cases.append({"image": name, "sidecar": sidecar_name, "counts": proposal["counts"],
                      "same_exact_occurrences_as_retained_baseline": matches == baseline_matches,
                      "input_binding_verified": spatial["input_binding_verified"],
                      "crop_to_raster_verified": spatial["crop_to_raster_verified"],
                      "page_location_status": "spatial-parent-only",
                      "model_reported_uncertainties": proposal["decoded_model_payload"].get("uncertainties"),
                      "withheld_vlm": [{"index": r["vlm_line_index"], "text": r["raw_text"],
                                        "reasons": r["withheld_reasons"]} for r in proposal["vlm_records"]
                                       if not r["candidate_eligible"]],
                      "unmatched_cpu": [{"index": r["cpu_index"], "raw_detection": r["raw_detection"],
                                         "reasons": r["review_reasons"]} for r in proposal["cpu_records"]
                                        if r["alignment_state"] != "unique_exact"]})
    after = {str(p.resolve()): digest(p) for p in paths}
    receipt = {"schema": "strong-line-offline-receipt/1", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "execution": "offline retained-input replay only", "network_or_model_calls": 0,
               "cpu_ocr_reinference_calls": 0, "gpu_operations": 0, "deployed": False,
               "whole_source_accepted": False, "all_original_inputs_unchanged": before == after,
               "original_input_sha256_before": before, "original_input_sha256_after": after,
               "cases": cases,
               "totals": {key: sum(c["counts"][key] for c in cases) for key in cases[0]["counts"]},
               "remaining_acceptance": "Parent must integrate and exercise actual GPU/UID999 worker; current worker remains MinerU1.2B + RapidOCR, 27B only QA probe."}
    write_json(output / "offline-receipt.json", receipt)
    print(json.dumps({"all_original_inputs_unchanged": receipt["all_original_inputs_unchanged"],
                      "cases": [{"image": c["image"], "counts": c["counts"],
                                 "baseline_matches": c["same_exact_occurrences_as_retained_baseline"]} for c in cases],
                      "totals": receipt["totals"]}, ensure_ascii=False, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.inputs, args.output)
