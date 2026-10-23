# Practical vision path — parent owns actual model/GPU tests

## Existing compatible assets, no download needed

- Installed model: `/home/adminz/llm/models/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored-v1.1.gguf`.
  Actual GGUF `general.architecture=qwen35`, `qwen35.embedding_length=5120`; SHA256 `3f83cab19428144f642969741f3143e53c6586fc27c7b2daece72787ad75b283`.
- **Projector already exists** alongside it: `mmproj-Qwen3.8-27B-BF16.gguf`, **931,146,528 bytes**, SHA256 `13cb7bebccbd04afc8f4090cb949ecf8937cdf7377c5799b1a0c594e7c0d3e16`.
  Actual GGUF: `clip.projector_type=qwen3vl_merger`, vision encoder27 blocks/1152 hidden/16 heads/16-pixel patches/spatial merge2; `clip.vision.projection_dim=5120`. These match the exact base Qwen official config (`Qwen3_5ForConditionalGeneration`, vision out_hidden_size5120), not a guessed 'qwen38' architecture.
- Publisher's exact compatible projector URL, pinned current revision:
  `https://huggingface.co/RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored/resolve/b5b12d28f0dcb90ccb041a2c977eae16b070a9d6/mmproj/mmproj-Qwen3.8-27B-BF16.gguf`
  File last commit `0fe4ddcc59be3db84402569eb16b5d66f5ad1cff`; HF LFS size/hash exactly match the installed file. Community quant/projector publisher, **not an official Qwen-produced quant**; official base config: `https://huggingface.co/Qwen/Qwen3.8-27B/blob/main/config.json`.
- Q8_0 alternative exists upstream:629,247,648 bytes, SHA256 `b280c2cb6ce46d6f81d9b2f976f145fc0d640c477e7932ab2ca0035d6dae6eea`; not downloaded, unnecessary while BF16 exists.
- Installed Strata launcher links `libllama-server-impl.so`; actual installed `libmtmd.so` contains `qwen3vl_merger`. Read-only source tree commit `3cf03257f219afbe7334045ff7c6a06ac68c627d` contains the Qwen3VL merger implementation and mmproj options. Current `/home/adminz/llm/config/qwen3-froggeric-v22.5.jinja` has explicit iterable `image/image_url` handling and `<|vision_start|><|image_pad|><|vision_end|>` (lines89–105). This is **static/metadata compatibility evidence, not an actual successful image generation or VRAM acceptance**.

## Parent-only measured test recipe

1. Use the existing exclusive T10-B scheduler contract and a dedicated vision QA process/port chosen by parent; preserve V100/T10-A and normal teaching return. No changes were made by this lane and no teaching/private generation endpoint was called.
2. Reuse the installed27B GGUF, add the exact existing BF16 `--mmproj`, retain the verified vision-capable template. Use a small dedicated context/batch rather than the teaching64k profile; start with context8192/parallel1 and reduced batch/ubatch. Disable speculative MTP for source-comparison repeatability; verify the installed runtime's exact supported flags. Measure reserve/load/vision-embedding peak and cleanup/return under the existing policy. `--no-mmproj-offload` may keep the projector on CPU if measured VRAM warrants it; do not assume any profile fits before measurement.
3. Send real local source PNG through standard multimodal user content (`text` plus `image_url` data URI), never put images in the system message. Prompt **literal source inventory only**: all printed labels/cells, normalized source boxes, table row/column hierarchy/spans or actual visible arrows with endpoint/direction/style; distinguish uncertainty; no exercise answers, inferred causal meaning or missing text invention. Retain raw exact response, source/image hash, recipe, finish reason/tokens.
4. Mandatory sources: corrected image+mask `p49-mask-corrected.png` and full original page49 (headings/boxes/arrows were genuinely erased by old RGB conversion), `src22/page8` jumbled-letter exercise, `src23/page4` weekday-picture matching, fresh QA table5.1 (`p3-b7-vlm`) and multi-level table5.7 (`p9-b20-vlm`), plus full QA page9. Fullpage vs crop are separate source evidence, not interchangeable.
5. Cross-check **literal values** against CPU polygons/source native where valid; check proposed table cell/edge geometry against the actual raster/mask. A list of detected words is not table spans/arrow direction or an answer mapping. New structured interpretations remain unverified unless real source-backed machine checks pass. Child receipt counts/tests are not this semantic gate.

## Fresh installed QA findings (read-only)

`qa-fresh-scan/read-only-diagnosis.json` binds10pages/202blocks to original src14 SHA. Existing old worker labelled177 blocks extracted,25needs_review; it has no finish metadata. Actual CPU postcheck of pages3/8/9 checks52 fullpage candidates:18 exact literal agreements, **0 verified under the new finish-aware gate**,22 paragraph texts also retained in whole-region output. This is not a quality approval or in-place reclassification.

Page9 primary whole-region response retains the table and ACTFL bullet box but omits much of the left prose and the right paragraph below the table. Actual region CPU detects121 lines/4664 normalized characters versus primary1736. Raw receipts and exact source PNGs are preserved. Table5.1 HTML concatenates bullet-list items inside each column; table5.7 requires real multi-level method/trait cell mapping. Correct-looking HTML or completed pages do not close those gates.
