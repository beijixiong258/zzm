# Coverage keys v1 (frozen now)

所有键和值为 JSON；无运行时绝对路径。不存在的组件不计为已读取。原schema1 required字段/page/block不变，仅manifest加source_format/preview_pdf/coverage。

## PDF/common

`version:1`, `representation:"original_pdf_pages"|"rendered_office_pdf_pages"`, `expected_pages`, `rendered_pages`, `page_set_complete`, `native_text_blocks`, `native_text_chars`, `source_image_occurrences`, `image_ocr_attempted`, `image_ocr_text`, `image_ocr_empty`, `image_decorative_uniform`, `image_reused_occurrences`, `image_untranscribed`, `literal_ocr_blocks`, `literal_ocr_chars`, `visual_interpretation_blocks`, `needs_review_blocks`, `semantic_accuracy_approved:false`, `all_visuals_transcribed:false`, `warnings:string[]`.

`complete=true`仅精确页集合/表示完成；**非**人工准确率、全部视觉语义完成。`image_untranscribed`包含native-only、选择页外、异常bbox、只有整页视觉候选而未单独literalOCR的image。均保留image资产与原位置。Hybrid最终策略对整页VLM也补充原image literal OCR，避免截图正文被layout当image interpretation后漏转录；不替换native/已有候选。`literal_ocr_blocks/chars`统计输出block/字符，full-page与region可能有重叠，**不是去重的原文字符数/准确率**。

## Office extension

`original_source_format`, `original_source_bytes`, `rendered_pdf_sha256`（派生PDF，仅coverage；顶层source_sha256必须仍为原OfficeSHA）, `rendered_pdf_pages`, `office_native_units`, `office_native_text_chars`, `office_media_parts`, `office_image_references`, `notes_count`, `notes_text_chars`, `notes_retained:true`, `notes_integrated_in_reading:false`, `office_auxiliary_parts_retained`, `office_raw_inventory:"raw/office-inventory.json"`, `hidden_slides`, `missing_components:string[]`。

PPTX页面数需等于原slide总数（包括hidden slides；转换ExportHiddenSlides=true）。Word页数只来自真实渲染PDF，不用原DOCX伪造页数。原XML/媒体和notes在raw内保留。不要把office_raw_inventory用作任意文件Serving。

计数定义：`notes_count`是保留的notes/auxiliary note **part**数量，不是非空speaker notes或单条comments数量；空footnote/endnote模板part也可能计入。PPTX为notesSlide part（本次原件27个），DOCX每个comments/footnotes/endnotes part计一个。`notes_text_chars`保留part文本聚合，可能包含slide-number占位文本；不得据此声称已索引speaker notes。`office_image_references`仅直接slide/main/header/footer XML中的blip引用，master/layout等保留于raw，不伪造其与PDF image/block的对应关系。Binary DOC辅助内容仅derived-DOCX inventory，原OLE streams仅metadata盘点；缺口通过warnings明示。

## Receipt metadata

逐页 `page_timings[i]`新增 `model_processed:boolean`、`model_calls:integer`、`imported_evidence:boolean`。model_calls统计指定loopback VLM端口实际POST generation的成功200响应（sync/async均观察）；health/models GET、别的端口、native、imported evidence、cache/uniform无新请求均0。空识字响应但真实请求200仍计true。整页MinerU可能每页多次请求；不可用mode字符串冒称0model pages。该metadata不是bundle schema扩展。

## Labels/IDs

- Native text: `issues`含`source_transcription_native`。
- Literal region OCR: `issues`含`source_transcription_ocr`；默认`quality=needs_review`；只有下述Stage14独立机器校验证据才可为`extracted`，从不`approved`；没有图边/题目答案重建。
- Whole-page VLM visual/table/etc: `visual_interpretation_unverified; not_literal_source_transcription`，`needs_review`。
- Image occurrence: `source_image_occurrence` + 处理/分类标签；uniform-only可判`image_class_decorative_uniform`，非uniform未识字不擅自判decorative。
- Region IDs：`pN-bDIGITS-region`（native索引总数+region序号），VLM IDs既有numericID加`-vlm`。无`pN-bregion`。

Packaging:3新依赖文件parse_material.py/office_inventory.py/archive_guard.py，与sibling document_stage12/parser_worker.py/parser_helpers.py一起；额外系统LibreOffice字体；现有Python PIL/pymupdf/mineru/olefile。无需python-pptx/docx（原XML直接bounded读取）。

## Stage14 optional evidence extension (schema1 required keys unchanged)

- 新runtime模块`material_stage13/ocr_verification.py`；CPU RapidOCR3.9.2仅使用既有local ONNX，实际三个session均须只有`CPUExecutionProvider`。缺包/权重或OCR失败有raw/receipt原因，不能伪造校验成功。
- `ocr_machine_verified_literal:raw/FILE.json[#BLOCK_OR_TRIAL]`标识机器校验：NFC+空白折叠（保留词边界/大小写/标点/数字）、两引擎逐字相等、全部CPU置信度>=.94、线性crop布局、真实generation finish为stop/eos。Unknown/length、refusal、近似匹配、非线性布局不放行。此tag只证明literal text，不证明graph/table关系、题目答案或人工语义批准。
- 整页OCR候选也默认needs_review；相同文字且几何重叠的fullpage重复块可excluded，但保留原ID/text/raw，`exact_overlapping_duplicate_of:ID`说明来源。非重复/冲突候选不合并、不替换native原文。高native字数不绕过实际CPU空间cross-check；不一致只降级并保留原文。
- Recovery IDs `pN-bDIGITS-region-recoveryK`；`targeted_literal_recovery; not_graph_relationships`。每图最多8tiles，每文默认64额外calls，可显式0..256。Raw保留全部primary/recovery响应、finish/tokens、原mask/image bytes/hash、CPU polygons/confidence、input-space tile bbox/rotation、未尝试CPU line indices。缓存每次occurrence仍有独立定位/registered assets及证明。
- Coverage新增optional计数`machine_verified_literal_blocks`、`targeted_recovery_blocks`、`native_independent_disagreement_blocks`、`excluded_exact_duplicate_blocks`。仍`semantic_accuracy_approved:false/all_visuals_transcribed:false`。
- PNG/APNG/WebP `coverage.original_image`保留全部display frame（含APNG default/poster）：`frames`、`frame_map[]`包含page/frame_index/duration_ms/default标志、原source SHA、原/正向尺寸、EXIF、decoded RGBA asset/hash、disposal/blend及loop。每个source frame<=16MP，derived render<=4MP，最多1000frames，decoded PNG累计<=100MiB、derived PDF<=64MiB。Corrupt/unsupported/超限在inference前显式失败。TXT/MD精确解码契约不变。

