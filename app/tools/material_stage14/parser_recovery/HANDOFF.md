# Parser recovery handoff — 源码与CPU实证，未部署

## 结果

- 已实现独立CPU OCR校验、实际finish/tokens观测、精确冲突记录、有限的定位tiling/90°与270°恢复、低置信度旧CPU错误的双引擎crop再校验、重复证据排除；不是批量改quality。只有逐字一致/高置信度/线性crop/真实stop或eos证据才`extracted`，从不`approved`。整页未校验候选不再默认可信。
- 找到并修复真正源输入缺损：原PDF soft mask被丢弃，p49黑线/标题在黑RGB背景上消失。实际原image+mask经当前helper合成白底后，PARTICIPANTS/PROCESSES/PRODUCTS、方框/箭头全部恢复可见；原image/mask bytes、SHA、native ID/bbox与transform保留。不是凭空补图。
- PNG/APNG/WebP全部bounded display frames入派生PDF/page map，含default/poster、duration/disposal/blend/loop/EXIF/alpha与原SHA。Corrupt late frame、1001frames、16MP超限在inference前失败；prepared复用不重复转换，TXT/MD exact contract未动。

## 实证与真实缺口

- `artifacts/stage14/parser-recovery/final-all-tests.xml`：**102passed +8subtests，0failure/error/skip**；包含parent原worker/schema/lease/adapter回归、frame/soft-mask/拒识/length/cancel/缓存每次occurrence/source-word边界/双栏crop/低置信度恢复及app真实bundle validator。OCR/VLM协议fixture明确不是GPU准确率证明。
- `cpu-source-comparison.json`：实际RapidOCR CPU13cases全部运行成功，7个原件前后SHA相同；native src20/page2真实乱码被空间cross-check触发降级信号。真实渲染ground-truth三行CPU逐字一致。**13cases仍未获整体OCR/语义通过**，原因/差异/置信度/原文均保留。
- Stage13真实失败：PPTX p10只有Evaluation/Pros/Cons/FACTS/EVIDENCE等源标签，旧response8654chars重复Prosservs/EVIDENCE；p1模糊照片旧response4096chars重复`1.`，CPU无文字。旧多句no-text解释不再伪作source transcription。不得把这些已有输出称为准确。
- 已按新增授权只读CT255 fresh QA原件/manifest/receipt/raw与选定PNG。10pages/202blocks/source SHA独立一致。`qa-cpu-comparison.json`：pages3/8/9真实CPU检查52fullpage blocks，18文字逐字一致，但缺旧finish证据，**0blocks按新gate verified**；22段文字同时保留在region输出。没有修改QA质量或CT/PVE文件。
- fresh QA p9 whole-region只输出table/ACTFL box，明显遗漏左栏正文和表后右栏段落：primary1736 normalized chars，CPU4664chars/121lines。Table5.1 HTML把同列bullets连接成一串；Table5.7多层Method/Trait关系不能靠字词列表批准。新恢复先选漏/冲突的dense source crops，而非只取头8个labels；预算之外line indices显式保留（p8当前8tiles规划34/87lines，p9为35/121lines），**不是全部修复完成**。

## parent接手

1. 包含新runtime模块`tools/material_stage13/ocr_verification.py`，用新的最终snapshot/package；parser1.2.0、material/simple1.1.0。旧cache不能冒充新校验结果。**r2 immutable snapshot未碰**。
2. parent改backend `source_identity`：真正decode/validate全frames，返回完整n_frames（含APNG poster），不要只改count。当前frame tests在旧admission处明确只验worker，未冒称app已兼容。
3. installed-user需RapidOCR3.9.2/CPU ONNX与权限/依赖实测。research已只读复用baseline现成包/31MiB级weights、现成native libs；没有改parent venv、下载权重或部署。缺依赖有明确unverified原因，不能因此称识别完成。
4. **视觉路径已具备，无须下载**：同27B的BF16 mmproj就在模型旁，931146528bytes/SHA `13cb7bebccbd04afc8f4090cb949ecf8937cdf7377c5799b1a0c594e7c0d3e16`。qwen35 text5120与qwen3vl_merger projection5120匹配；实际libmtmd/template含image支持。仅静态/metadata证明，实际image generation/VRAM和图表语义仍由parent独占T10-B测试。精确URL/revision与recipe见`VISION_PATH.md`。

## 文件/边界

修改：`document_stage12/{parser_worker,parser_helpers}.py`，`material_stage13/{simple_material,parse_material}.py`与`COVERAGE_KEYS.md`，`material_stage14/test_simple_material.py`。新增runtime `material_stage13/ocr_verification.py`，probe/tests/集成/视觉说明均在`material_stage14/parser_recovery/`；证据仅在`artifacts/stage14/parser-recovery/`。

权威状态：`verification-summary.json`；isolated CPU transport两文件逐byte读回匹配：`cpu-code-readback.json`。初次依赖/fixture失败证据保留，未以成功覆盖失败解释。没有backend/frontend/supervisor/scheduler/bridge/installer修改，没有GPU/model start/stop/generation，没有生产DB/env/keys读取或PVE/CT写入。当前lane无运行中的owned probe，代码可交回parent；全5232images语义完成与真实新GPU恢复、应用reading/citation/promote仍是parent gates。
