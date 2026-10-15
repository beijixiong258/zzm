# Stage13 parser handoff — 2026-10-11，12:35 CST前交还所有权；未部署

## 实现/接口

- 保留schema1 required/page/block字段；新增`source_format`、Office必需`preview_pdf="preview.pdf"`、`coverage`。完整键/定义见[COVERAGE_KEYS.md](COVERAGE_KEYS.md)。没有新block字段；语义角色通过`issues`区分native/literal OCR/unverified interpretation。IDs保持`pN-bDIGITS[-suffix]`。
- Entry：`tools/material_stage13/parse_material.py --input ORIGINAL --output FRESH_DIR [--source-format pdf|pptx|docx|doc]`。既有`--engine hybrid --vlm-url --vlm-device cuda --models --dpi --deadline-seconds`原样兼容；PDF也可继续直接parser_worker。输入路径须保留trusted原suffix，否则显式source-format。Sibling `../document_stage12`布局兼容parent计划的code-stage13。
- Mixed PDF：native_chars>=40不再跳过image text；自动取原embedded raster做literal Text Recognition，保留每次出现的page/bbox/native ID/image assets及几何parent。最终hybrid对whole-page VLM也补充image literal OCR，避免截图正文被layout当image interpretation后漏转录。每张实际OCR input PNG和原embedded bytes均留raw；显式regions仍用final-raster crop。Exact OCR-image cache复用但不合并不同occurrence；uniform decorative单独分类。native正文不替换、不截50k；坏font mapping保留原文并needs_review。
- Whole-page MinerU候选与native合并；visual/table/other/equation为unverified interpretation、needs_review。独立`-vlm` crop文件，避免native asset被同index覆盖。明确拒识/无文字模板响应保留raw，不冒充source transcription。不生成图边/字母题答案。
- Office：Linux headless LibreOffice，readonly staging copy、每job独立profile、MacroSecurityLevel3、Writer Link update2（Never）、4线程、8GiB virtual-address上限、6GiB available-memory reserve、120s单次转换上限。原Office SHA永远是顶层身份；DOC另转DOCX做native/auxiliary inventory，preview PDF只是派生表示。PPTX包括hidden slide并核对所有sldId数量；Word只用真实PDF页数。
- 在Office readers/LO之前校验实际ZIP deflate输出/CRC/central directory，64MiB输入、100MiB expanded、4096members、16MiB XML、no entities/macros/external linked content/path traversal/symlinks、16MP source raster。PDF1000pages/<4MP render保护保留。Existing output不覆盖；failed receipt/raw保留；返回bundle不含symlinks。
- `manifest.warnings`明确notes/auxiliary/raw-only、未进入student reading；binary DOC OLE仅metadata inventory，辅助语义仅derived-DOCX，不声称完整解码。
- Receipt逐页有`model_processed`/`model_calls`/`imported_evidence`：观察指定VLM端口成功generation POST，native/import/cache/health/别的端口0；空识字响应实际请求仍true。Office完整保留脱敏`raw/pdf-parser-receipt.json`，失败不丢准确child cause。

## 已完成验证

### 所有23原件（不等同全部视觉语义完成）

- Ubuntu full native表示**23/23成功，1338页**：18PDF/2DOCX/2DOC/1PPTX。独立再次对每页original或derived-PDF读取：**37,801 native blocks /1,755,098 chars/5,232 image occurrences**；每个native ID/text/original bbox均相等。23原SHA/bytes与既有sources.json相符，处理后未变。
- 317页guide：269/317定位、97页异常bbox原证据/needs_review fallback均保留。
- Office真实完整页数：src11 DOCX2、src15 PPTX27、src16 DOC6、src17 DOCX8、src19 DOC2。PPTX33,801,748 bytes（原25MiB挡住的真实输入）已内部转换；73media parts、27notes parts/3878raw text chars保留。notes_count定义是part数量，含可能空模板/slide-number文本，**不是已经索引的speaker notes**。
- Artifact：`artifacts/stage13/parser/native-probes-23.json`、`native-source-readback.json`、`final-source-state-readback.json`、**`verification-summary-final.json`**（最终权威状态；其余summary是历史）。完整private bundles只在Ubuntu research目录，未部署。最终source-state回读再次23/23、所有原SHA/ID/text/bbox不变。

### GPU representative/final

- `gpu-final-result.json`是**补充OCR前版本**：mixed PDF65页（只选择5/6/49做OCR）、PPTX27页（13/24）、DOCX8页全部image OCR、DOC6页全部image OCR、原10页scanned chapter whole-hybrid全部通过。全部native IDs/text、原身份保留。不得把该scan通过冒称当前final code通过。
- Mixed source49图中文字9个labels与原OCR input目视相符，没有重建arrows；PPTX13 Graphic Design/IS MY/PASSION与图相符。已知sample23 jumbled-letter/order风险仍不自动建立mapping，更不解题；原有curation/fixtures没改。
- Fresh-model receipt验证：mixed page5=3calls/true，page6=0/false（cache）、page49=1/true；PPTX13=6/true，24uniform=0/false；DOCX8model pages/8calls，DOC5/5；原10page scanned231calls，literal OCR51,298chars（未截50k）。该engine整页visual interpretations仍needs_review。
- 上述早期T10-B probe min free469MiB；随后default whole-Office旧hybrid min227MiB。**最终additive batch min159MiB，触发既有200MiB reserve guard，aggregate exit2**。三teaching GPU PIDs/config不变、workers healthy、owned18894/server/parser均已关闭；独立`final-runtime-readback.json`也确认port closed/healthy。V100真实短generation200/READY约0.48s（teaching-companion.json），不是长期负载/教学质量证明。没有shared service restart/GPU eviction/lease部署。

### Focused/CPU/safety

- 最终17 focused unittest、6 legacy schema/helper tests通过；3实际PDF allocation-limit cases通过（1001pages、16MP raster、4MP giant render）；4真实Linux Office synthetic cases通过（hidden slide2pages/1hidden/2notes、nooverwrite、>64MiB preflight、deadline failure保留原身份）。
- 覆盖duplicate same-bbox occurrence parentage/cache、70k正文保留、refusal不索引、sync/async successful-empty模型计数、非VLM端口不计、imported0calls、visual crops不覆盖native assets。原scanned10所有native crop逐个像素等于自己的rendered-page region。

## 失败及修复

1. 初次PPTX conversion在3GiB address limit两次Signal11（记录`pptx-failure-v1/v2.json`）；实际同源改8GiB bounded AS、SAL_MAX_CONCURRENCY4后通过。不改GPU/系统packages。
2. **实际full-office default hybrid初次PPTX失败**：conversion正确，但剩余deadline带fraction，MinerU Config `model.vlm.http_timeout`只收int，触发`int_from_float`。准确原始cause保留`pptx-exact-child-failure.json`（79.420469…）。将该HTTP timeout floor成int，整体SIGALRM/wall deadline没放宽，结构/来源guard没放宽；adapter增加准确child receipt保存。fractional-budget regression已通过。
3. Fixed default whole-Office初版真实通过27/8/6页；但DOC16只有1023literal chars/8unverified interpretation，少于同源region7160，说明layout成功不是全部图片正文文字转录。最终增加whole-VLM上的原image literal OCR，不放宽任何source/structure/resource guard。
4. **当前final code的default whole-Office3个真实case通过**：PPTX27页212.35s/154model calls、DOCX8页80.81s/162calls、DOC6页60.12s/23calls；全部原SHA/native IDs/text保留，derived PDF页数匹配，三个`image_untranscribed=0`。literal OCR output分别41862/15958/7165chars；full-page/region可重叠，不是去重原文字数/准确率。
5. **最终aggregate不通过**（`additive-literal-final-result.json`）：同一VLM跨3个Office case复用后，进入legacy scan时probe观测free159MiB<200，MemoryError停止仅owned进程。scan child保留`ReadTimeout`及`worker total wall deadline reached`消息，0completed pages；该消息来自共用SIGTERM/SIGALRM handler/HTTP包装，**不能当作430s wall budget实际耗尽**。准确guard原因和GPU样本/cleanup在aggregate receipt中，原scan failed receipt在`additive-scan-failed-receipt.json`，没有抹掉失败。
6. 此probe复用同一VLM跨cases，production按document启动/停止。**不得把batch失败推断为fresh-per-document scan必然失败**；final-code fresh-server全10页未在12:35前完成验收，未降低200MiB guard、未缩图降质换绿、未停止teaching。交由parent在充足资源/明确lease下重新验收。

## 部署前仍由parent验收

- 最终runtime代码5个文件：parser_worker.py/parser_helpers.py以及material_stage13/{parse_material.py,office_inventory.py,archive_guard.py}。其余new *.py是tests/probes，*.md是接口/交付说明。**`artifacts/stage13/parser/code-hashes.json`**列11个Python文件SHA/bytes；`final-runtime-readback.json`确认11/11与Ubuntu实际运行代码逐byte相符。
- 此lane只有adminz research venv/目录的正式Ubuntu parser/model运行证明；不是installed `aicademiya-docs` user、restricted SSH bridge或完整application acceptance。请在最终package验证这三项及publication/old-new editions/citations/original-download/derived-PDF endpoints。
- Runtime Python依赖：pymupdf/Pillow/httpx/mineru/mineru_vl_utils，DOC还需olefile（research venv已有，installed venv须独立readback）；python-pptx/docx不属于adapter运行依赖（仅synthetic test用pptx）。系统LibreOffice Writer/Impress+fonts由parent安装。
- 不能宣称23源全部5,232 images已OCR/准确理解；native ledger是表示覆盖，GPU probes有明确范围。Region literal OCR仍needs_review；notes/auxiliary/off-slide/embedded objects未进入authoritative teaching evidence。`complete=true`仅精确page-set/表示完成，不能等同all source components/accuracy。多document/长材料资源稳定性和scheduler rollout未验证/未部署；old production rollback code未动。
- 没有backend/frontend/supervisor/bridge/installer/生产文件写入，未部署。Original材料只读。

## Ubuntu evidence / reproducible commands

Research root：`/home/adminz/llm/ocr-stage1-20261009/stage13-parser`；Python：existing `whole-document-pilot/.venv/bin/python`。运行`tools/material_stage13/{run_native_probes,verify_native_ledger,run_gpu_probes,test_material_parser,test_office_execution}.py --help`看各probe参数；GPU probe只绑定owned18894、显式T10-B、检查idle/VRAM/health、bounded cleanup。**run_gpu_probes.py还含本lane专属2026-10-11 12:30 CST hard stop，parent后续另行授权的验证须显式调整该test-only时间界限或用自身runtime probe；不能原封不动当长期production runner。**不要把probe当production GPU owner/scheduler。

Code/ownership finalization：**已交还parent所有parser/new tools所有权；从此不再修改。无running owned jobs/servers。此交付不是deployment approval；最终scan gate与installed-user/app acceptance仍是明确未完成项。**
