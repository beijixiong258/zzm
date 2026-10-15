"""Strict monotonic literal evidence alignment, not source approval.

A maximum-cardinality ordered alignment is computed globally. A line is uniquely
aligned only if its SAME contiguous CPU group is mandatory in EVERY optimum.
Repeated text with multiple equally good occurrences is withheld, never greedily
assigned. Only NFC/layout whitespace equivalence is imported from current parser.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re
import json

from tools.material_stage13.ocr_verification import normalized

MIN_CPU_CONFIDENCE = 0.94


def parse_lines(content: object) -> tuple[list[str], object, list[str]]:
    if not isinstance(content, str):
        return [], None, ["missing_model_content"]
    text = content.strip()
    if text.startswith("```"):
        fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if not fence:
            return [], None, ["invalid_json_fence_or_trailing_content"]
        text = fence.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [], None, ["invalid_line_json"]
    if not isinstance(parsed, dict) or not isinstance(parsed.get("lines"), list):
        return [], parsed, ["invalid_lines_schema"]
    if any(not isinstance(line, str) for line in parsed["lines"]):
        return [], parsed, ["non_string_line"]
    errors = []
    if not isinstance(parsed.get("uncertainties"), list):
        errors.append("missing_or_invalid_uncertainties_array")
    return parsed["lines"], parsed, errors


def ordered_alignment(vlm_lines: list[str], cpu_lines: list[dict], max_cpu_group: int = 2) -> dict:
    if not isinstance(max_cpu_group, int) or isinstance(max_cpu_group, bool) or not 1 <= max_cpu_group <= 3:
        raise ValueError("max_cpu_group must be 1..3 contiguous detections")
    n, m = len(vlm_lines), len(cpu_lines)
    vtext = [normalized(t) for t in vlm_lines]
    ctext = [normalized(line["text"]) if isinstance(line.get("text"), str) else "" for line in cpu_lines]
    groups = {}
    for i in range(n):
        if not vtext[i]:
            continue
        for j in range(m):
            for length in range(1, min(max_cpu_group, m - j) + 1):
                # No empty detections can be hidden inside a group.
                if all(ctext[j:j + length]) and normalized(" ".join(ctext[j:j + length])) == vtext[i]:
                    groups.setdefault((i, j), []).append(length)
    forward = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            value = forward[i][j]
            if i < n:
                forward[i + 1][j] = max(forward[i + 1][j], value)
            if j < m:
                forward[i][j + 1] = max(forward[i][j + 1], value)
            for length in groups.get((i, j), []):
                forward[i + 1][j + length] = max(forward[i + 1][j + length], value + 1)
    backward = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            options = [0]
            if i < n:
                options.append(backward[i + 1][j])
            if j < m:
                options.append(backward[i][j + 1])
            options.extend(1 + backward[i + 1][j + length] for length in groups.get((i, j), []))
            backward[i][j] = max(options)
    optimum = forward[n][m]
    records = []
    stable_cpu = set()
    possible_cpu = set()
    for i in range(n):
        alternatives = []
        for j in range(m):
            for length in groups.get((i, j), []):
                if forward[i][j] + 1 + backward[i + 1][j + length] == optimum:
                    indices = list(range(j, j + length))
                    alternatives.append(indices)
                    possible_cpu.update(indices)
        skip_possible = any(forward[i][j] + backward[i + 1][j] == optimum for j in range(m + 1))
        if len(alternatives) == 1 and not skip_possible:
            state = "unique_exact"
            indices = alternatives[0]
            stable_cpu.update(indices)
        else:
            state = "ambiguous_exact" if alternatives else "unmatched"
            indices = []
        records.append({"vlm_line_index": i, "alignment_state": state,
                        "cpu_indices": indices, "optimal_cpu_group_alternatives": alternatives,
                        "can_be_unmatched_in_optimum": skip_possible})
    return {"optimal_exact_group_count": optimum, "vlm": records,
            "cpu": [{"cpu_index": j, "alignment_state": "unique_exact" if j in stable_cpu else
                     "ambiguous_exact" if j in possible_cpu else "unmatched"} for j in range(m)]}


def valid_confidence(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and MIN_CPU_CONFIDENCE <= value <= 1)


def valid_geometry(line: dict) -> bool:
    box = line.get("bbox")
    polygon = line.get("polygon")
    def unit(value):
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and 0 <= value <= 1)
    if not isinstance(box, list) or len(box) != 4 or not all(unit(v) for v in box):
        return False
    if box[0] >= box[2] or box[1] >= box[3]:
        return False
    if not isinstance(polygon, list) or len(polygon) < 3:
        return False
    if any(not isinstance(p, list) or len(p) != 2 or not all(unit(v) for v in p) for p in polygon):
        return False
    # Retain original polygon and box; inconsistent geometry is not silently fixed.
    expected = [min(p[0] for p in polygon), min(p[1] for p in polygon),
                max(p[0] for p in polygon), max(p[1] for p in polygon)]
    return all(abs(a - b) <= 1e-6 for a, b in zip(box, expected))


def line_location(indices: list[int], cpu_lines: list[dict], spatial: dict) -> dict:
    result = {"page_location_status": "spatial-parent-only",
              "spatial_parent": spatial.get("spatial_parent"),
              "coordinate_space": "ocr_input_normalized",
              "cpu_geometry": [{"cpu_index": j, "bbox": deepcopy(cpu_lines[j].get("bbox")),
                                "polygon": deepcopy(cpu_lines[j].get("polygon"))} for j in indices],
              "source_raster_mapping_status": "unproven"}
    if not indices or not all(valid_geometry(cpu_lines[j]) for j in indices):
        return result
    if spatial.get("crop_to_raster_verified") is not True:
        return result
    width, height = spatial["input_size"]
    left, top, _, _ = spatial["crop_pixels"]
    scale = spatial["scale"]
    mapped = []
    for j in indices:
        poly = [[left + p[0] * width / scale, top + p[1] * height / scale]
                for p in cpu_lines[j]["polygon"]]
        mapped.append({"cpu_index": j, "polygon_pixels": poly,
                       "bbox_pixels": [min(p[0] for p in poly), min(p[1] for p in poly),
                                       max(p[0] for p in poly), max(p[1] for p in poly)]})
    boxes = [x["bbox_pixels"] for x in mapped]
    result.update(source_raster_mapping_status="verified_crop_scale_only",
                  source_raster=spatial.get("source_raster"), source_raster_geometry=mapped,
                  source_raster_group_bbox_pixels=[min(b[0] for b in boxes), min(b[1] for b in boxes),
                                                   max(b[2] for b in boxes), max(b[3] for b in boxes)])
    # No raster->document-page proof exists in these inputs. Never relabel as page bbox.
    return result


def uncertainty_indices(parsed: object, count: int) -> tuple[set[int], bool]:
    uncertain = set()
    global_uncertainty = False
    if not isinstance(parsed, dict) or not isinstance(parsed.get("uncertainties"), list):
        return uncertain, True
    for entry in parsed["uncertainties"]:
        if not isinstance(entry, dict):
            global_uncertainty = True
            continue
        index = entry.get("line_index")
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < count:
            uncertain.add(index)
        else:
            global_uncertainty = True
    return uncertain, global_uncertainty


def align_evidence(cpu_scan: dict, generation: dict, spatial: dict, *,
                   evidence_kind: str = "unclassified_offline_evidence",
                   region_kind: str = "unknown", max_cpu_group: int = 2) -> dict:
    """Pure sidecar proposal API. Inputs are never mutated; raw records preserved.

    spatial input binding must be established separately (offline.verify_spatial).
    No output is a manifest, approved block, table topology, or semantic reading.
    """
    vlm_lines, parsed, parse_errors = parse_lines(generation.get("content"))
    cpu_lines = cpu_scan.get("lines", [])
    if not isinstance(cpu_lines, list) or any(not isinstance(line, dict) for line in cpu_lines):
        raise ValueError("CPU lines must be an array of raw detection objects")
    alignment = ordered_alignment(vlm_lines, cpu_lines, max_cpu_group)
    global_reasons = list(parse_errors) + list(generation.get("protocol_errors", []))
    if generation.get("finish_reason") != "stop":
        global_reasons.append("missing_or_non_stop_finish")
    if generation.get("finish_provenance") not in {
        "openai_compatible_response_choice", "archived_real_probe_case"}:
        global_reasons.append("finish_not_from_actual_transport_or_archived_probe_metadata")
    if (cpu_scan.get("status") != "complete" or cpu_scan.get("available") is not True
            or cpu_scan.get("engine") != "rapidocr-onnx-cpu"
            or cpu_scan.get("actual_providers") != ["CPUExecutionProvider"]):
        global_reasons.append("independent_cpu_evidence_not_complete")
    if spatial.get("input_binding_verified") is not True:
        global_reasons.append("unverified_model_cpu_input_binding")
    if (not isinstance(generation.get("input_image_sha256"), str)
            or generation.get("input_image_sha256") != spatial.get("input_sha256")):
        global_reasons.append("model_input_image_hash_mismatch_or_missing")
    if (cpu_scan.get("input_size") != spatial.get("input_size")
            or cpu_scan.get("input_pixel_sha256") != spatial.get("input_pixel_sha256")):
        global_reasons.append("cpu_input_pixel_or_size_mismatch")
    uncertain, global_uncertainty = uncertainty_indices(parsed, len(vlm_lines))
    proposals = []
    vlm_records = []
    for record in alignment["vlm"]:
        i = record["vlm_line_index"]
        indices = record["cpu_indices"]
        reasons = list(global_reasons)
        if record["alignment_state"] != "unique_exact":
            reasons.append("multiple_optimal_occurrences" if record["alignment_state"] == "ambiguous_exact"
                           else "no_exact_independent_match")
        if global_uncertainty or i in uncertain:
            reasons.append("model_reported_or_unscoped_uncertainty")
        if indices and any(not valid_confidence(cpu_lines[j].get("confidence")) for j in indices):
            reasons.append("independent_confidence_below_0.94_or_invalid")
        if indices and any(not valid_geometry(cpu_lines[j]) for j in indices):
            reasons.append("invalid_independent_source_geometry")
        location = line_location(indices, cpu_lines, spatial)
        reasons = list(dict.fromkeys(reasons))
        entry = {**record, "raw_text": vlm_lines[i], "candidate_eligible": not reasons,
                 "withheld_reasons": reasons, "location": location}
        vlm_records.append(entry)
        if not reasons:
            proposals.append({"proposal_id": f"vlm-line-{i}", "proposal_kind": "literal_text_evidence",
                              "state": "candidate_only", "raw_text": vlm_lines[i],
                              "comparison_text_nfc_layout_whitespace": normalized(vlm_lines[i]),
                              "vlm_line_index": i, "cpu_indices": indices,
                              "minimum_cpu_confidence": min(cpu_lines[j]["confidence"] for j in indices),
                              "finish_reason": generation["finish_reason"], "location": location,
                              "structure_status": "unverified", "semantic_status": "not_evaluated"})
    cpu_records = []
    for record in alignment["cpu"]:
        j = record["cpu_index"]
        reasons = []
        if record["alignment_state"] == "unmatched":
            reasons.append("cpu_only_or_literal_disagreement")
        elif record["alignment_state"] == "ambiguous_exact":
            reasons.append("multiple_optimal_occurrences")
        if not valid_confidence(cpu_lines[j].get("confidence")):
            reasons.append("independent_confidence_below_0.94_or_invalid")
        if not valid_geometry(cpu_lines[j]):
            reasons.append("invalid_independent_source_geometry")
        cpu_records.append({**record, "raw_detection": deepcopy(cpu_lines[j]), "review_reasons": reasons,
                            "location": line_location([j], cpu_lines, spatial)})
    return {"schema": "strong-line-evidence-proposal/1", "state": "sidecar_proposal_only",
            "evidence_kind": evidence_kind, "deployed": False, "gpu_acceptance": False,
            "whole_source_accepted": False, "region_kind": region_kind,
            "structure_status": "unverified", "semantic_status": "not_evaluated",
            "structure_warning": "Linear text evidence does not verify table cells, hierarchy, graph edges, or figure relationships.",
            "method": "Global monotonic maximum-cardinality exact NFC/layout-whitespace alignment; mandatory identical occurrence across all optima; contiguous CPU groups only",
            "minimum_cpu_confidence": MIN_CPU_CONFIDENCE, "max_cpu_group": max_cpu_group,
            "global_withheld_reasons": list(dict.fromkeys(global_reasons)),
            "spatial_context": deepcopy(spatial), "raw_cpu_scan": deepcopy(cpu_scan),
            "raw_generation": deepcopy(generation), "decoded_model_payload": deepcopy(parsed),
            "vlm_records": vlm_records, "cpu_records": cpu_records, "text_candidates": proposals,
            "counts": {"vlm_lines": len(vlm_lines), "cpu_detections": len(cpu_lines),
                       "optimal_exact_groups": alignment["optimal_exact_group_count"],
                       "unique_exact_groups": sum(r["alignment_state"] == "unique_exact" for r in vlm_records),
                       "ambiguous_vlm_lines": sum(r["alignment_state"] == "ambiguous_exact" for r in vlm_records),
                       "unmatched_vlm_lines": sum(r["alignment_state"] == "unmatched" for r in vlm_records),
                       "unmatched_cpu_detections": sum(r["alignment_state"] == "unmatched" for r in cpu_records),
                       "low_confidence_cpu_detections": sum(not valid_confidence(l.get("confidence")) for l in cpu_lines),
                       "text_candidates": len(proposals), "withheld_vlm_lines": len(vlm_records) - len(proposals)}}
