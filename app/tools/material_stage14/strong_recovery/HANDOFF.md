# 强视觉逐行恢复适配器交接（未部署）

## 交付结论

仅新增 `tools/material_stage14/strong_recovery/` 与 `artifacts/stage14/strong-recovery/`；没有修改 parser/backend/frontend/worker/scheduler、既有 manifest 或原件，没有操作模型/GPU/lease/root/部署服务。

- 留存真实输入离线重放：p1 的 24 条 VLM 行 / 25 个 CPU 检测得到 **23** 个文字证据候选；p9 的 39 条 / 40 个检测得到 **34** 个候选。每一个候选的 VLM/CPU occurrence indices 都与已有 `line-alignment.json` 完全一致。
- 合计保留 63 条模型行、65 个 CPU 检测；57 个候选，6 条未匹配模型行、6 个未匹配 CPU 检测（含 2 个低置信检测）均原样保留，没有补写缺失内容。
- 33 项 unittest + 74 个 subtest 通过；其中 1 项测试另用 270 个有限序列组合与独立穷举最优对齐 oracle 比较，验证重复行/合并行/顺序歧义。完整回执与日志见下。
- 两个 crop 都通过文件 SHA、CPU RGB+size hash、尺寸与 **LANCZOS 重建 RGB 像素逐字节相同**验证。因此 crop → 原 raster 坐标可溯源；**没有 raster → 文档页放置变换证据**，所有文档页定位仍为 `spatial-parent-only`，没有生成 page bbox 或引用。
- 这是文字证据 sidecar 提案，不是 approved/extracted manifest、整页或整文完成声明。表格/图示结构统一 `unverified`，语义 `not_evaluated`。

## 文件与 API

| 文件 | 用途 |
|---|---|
| `protocol.py` | `LoopbackLineClient` 与可注入 `HTTPReply` transport；固定源忠实提示；OpenAI-compatible `/v1/chat/completions`，显式 numeric loopback host/port，非流式，temperature=0；保存原始 request/response bytes 的 base64/SHA、response headers/status、parsed 原对象、实际 choice finish 与 usage |
| `alignment.py` | 纯函数 `align_evidence(cpu_scan, generation, spatial, *, evidence_kind, region_kind, max_cpu_group=2)`；不改输入，不调用网络/模型；严格按源顺序的全局最优对齐与保留未决项 |
| `offline.py` | `verify_spatial()` 验证真实同输入与 crop/scale；`archived_generation()` 明确标记历史真实 QA case 元数据；`run()` 只读既有资料并向自己的 artifact tree 输出 |
| `test_strong_recovery.py` | 真实留存输入、重复行、低置信、异常 finish、漏行、多写、字形/标点/数字、定位和协议 fixture 测试 |
| `run_tests.py` | 完整 unittest 日志、每项测试/子测试 outcome、源码 SHA 与运行环境回执 |
| `__init__.py` | 窄公开 API：client / HTTPReply / align_evidence |

### 客户端接口

```python
from tools.material_stage14.strong_recovery import LoopbackLineClient

# 仅示例，未执行真实模型请求。父集成方负责既有生命周期与已授权 lease。
client = LoopbackLineClient("http://127.0.0.1:PORT/v1", "explicit-model-alias")
# capture = client.transcribe(image_bytes, evidence_kind="actual_model_capture_pending_worker_acceptance")
```

`PORT` 是文档占位符，不是可运行配置。使用明确现存 loopback 端点，不由适配器发现/启动端点。固定提示不接受 caller override，要求保留不常见源拼写、大小写、标点、数字、符号、bullet 和行尾连字符，不从上下文补全、不推断图表关系。输入图片不会注入 CPU 识读文本。

transport 签名是 `(endpoint: str, body: bytes, timeout: float) -> HTTPReply(status, headers, body)`。HTTP 走 `http.client`，不跟随 redirect，不读 proxy environment；没有重试、server 管理、模型装载、GPU 控制或多 reviewer。失败保存 request 和真实 error，绝不伪造 response。实际 HTTP 测试只是临时 loopback **protocol fixture**，服务已关闭，回执显式 `gpu_acceptance=false`。

### 对齐与候选闸门

1. 复用只读 `tools/material_stage13/ocr_verification.py:normalized`，只做 NFC + 布局空白，绝不大小写/标点/数字/字形纠正。测试时该文件 SHA 为 `1649770889ca88e017fd426de8c96f97531d0d71e354489458cace1324066748`。
2. 一条 VLM 行可对应 1–2 个相邻 CPU 检测（API 可明确选择 1–3）；不跨越中间检测拼凑。DP 最大化严格字面匹配的 VLM 行组数量，保持双方原顺序。不是贪婪找相同句子。
3. 枚举所有最优路径中的 match edge。只有该行在**每一个最优方案中都必须对应同一个 CPU group**，才标记 `unique_exact`；重复 occurrence 歧义列出全部 group alternatives，并 withheld，不任选一个 bbox。重复两行在两边唯一顺序对应时可以正常匹配。
4. 文字候选还必须：真实 transport choice 或原始留存 real probe metadata 的 `finish_reason == "stop"`；没有协议/JSON/schema 错误；独立 RapidOCR CPU complete 且 CPUExecutionProvider；VLM 文件 hash 与 CPU RGB+size hash 同输入绑定；组内每个 confidence 均 >=0.94 且有效；bbox/polygon 一致有效；没有该行/全图模型 uncertainty。
5. 模型声称 `uncertainties=[]` 不增加证据权重；缺失/无效 uncertainty metadata 会 withheld；模型正文自称 finish 不代替 transport finish。
6. 只 `text_candidates` 是通过这些字面闸门的候选，`state=candidate_only`。`vlm_records` 与 `cpu_records` 保存所有条目，包括低置信、CPU-only、model-only、歧义及 withheld 原因。`raw_generation` / `raw_cpu_scan` / `decoded_model_payload` 均保留；原始 model content 从不清理/改写，围栏仅用于解析视图。

`spatial` 的输入绑定证明是 API 调用方责任，应使用 `verify_spatial` 或父级已验证同等流程；不能把自行填入的 True 当证明。这个窄适配器不建立通用证据签名框架。只要同输入绑定成立，缺少 crop→raster 映射时仍可生成文字候选，但只挂 parent，绝不猜精确位置。

## 真实输入结果与不能绕过的未决点

- p1 VLM line 15 原文输出 `Margorgo`，CPU detection 16 原文保留 `Margoargo`，该行**不产候选**。`source-name-disagreement.json` 记录的是父会话实际 sourcecrop 观察：raster 拼写就是 **Margoargo**，不是常见的 Margo。本子任务没有重新宣称视觉审核或人工批准。
- p9 VLM 未匹配行 index 为 16/18/19/33/38，CPU 未匹配 detection 为 17/19/20/34/39；两条 CPU 乱码 confidence 为 0.65402/0.63975；另外保留 `page 110` / `page110` 以及 bullet 有/无差异，不抹掉标点来凑一致。
- 未匹配 VLM 行没有独立对应 bbox，只有 source-raster parent。未匹配 CPU 条目可以保留自己的已验证 raster 位置，但不是 VLM 文字的位置。
- crop→raster 公式：`x = crop_left + input_normalized_x * input_width / scale`，`y = crop_top + input_normalized_y * input_height / scale`。保留每个 CPU polygon 与其 source-raster polygon；group bbox 只是这些检测几何的 envelope，不是表格单元或语义边界。
- 已有真实 `vision-lines-r3-result.json` **不是本客户端执行结果**。它保留 case content/finish/usage 等，但没有完整原始 HTTP wire bytes。输出明确 `raw_wire_http_response_available=false`，没有伪造历史 HTTP response。整份原始 JSON 被逐字节复制，模型 content 单独以其 UTF-8 精确字节留存。新客户端仅由 fixture 测试证明协议与 raw capture 行为。

## 产物和完整回执

`artifacts/stage14/strong-recovery/`：

- `p1-left-page-2x.proposal.json`、`p9-left-page-2x.proposal.json`：完整文字候选 sidecar，原始扫描/生成、全部行、歧义/未匹配项、同输入证明和坐标限制。
- `offline-receipt.json`：全部 count、与原对齐 occurrence 一致性、原件 SHA before/after（全部相同）；离线网络/model/GPU 调用均为 0。
- `retained-inputs/`：5 份原始 JSON 逐字节副本（vision result / CPU / transforms / 原 alignment / 源姓名差异记录）。
- `raw-content/`：两个 case 的精确 content UTF-8 字节；不是重新生成内容。
- `test-receipt.json` + `tests.log`：33 项测试与 74 个 subtest 无失败/错误/跳过，运行环境、测试列表、源码 SHA。270 组 oracle 是其中一项测试的内部组合数，**不夸大成 270 项 unittest**。
- `protocol-http-fixture-receipt.json`：真实临时 loopback HTTP 交换、完整 request/response bytes/hash/finish/usage 及 fixture 服务关闭证明；**不是 GPU 通过回执**。

从 `D:/HermesProjects/EDUC7703/app` 复现（不额外安装依赖；现有 `.venv` 与 Pillow 即可）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -B -m tools.material_stage14.strong_recovery.offline
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -B -m tools.material_stage14.strong_recovery.run_tests
```

`-B` 避免给只读父模块写 pycache。仅输出自己的 artifact tree。离线脚本对真实输入执行 SHA 和 pixels 校验，不重新执行 CPU OCR。Linux 父级移植时改用其现有 document venv 的 python、重置输入文件位置，保留内容 SHA；本交付没有 Linux/GPU/UID999 实测。

## 父集成建议 / 剩余验收

1. **当前 GPU worker 仍是 MinerU1.2B + RapidOCR；27B 只是 QA 探测，没有接入 worker/app。** 本子任务不能替代父会话正在做的 mask+geometry 修复、打包、备份或部署。
2. 父集成可在现有已授权 lease/lifecycle 下，把必要源 crop 交给 client，并让独立 `CPUVerifier.scan` 读取同一确定的 RGB 输入。将 capture 的 `generation`、真实 CPU scan 和由源 raster/crop/scale 验证生成的 `spatial` 交给 `align_evidence`。对新 live capture 的 `input_image_sha256` 与 `spatial.input_sha256` 必须相同。raw capture 在进入 proposal 前即持久化；中断/失败也保留。
3. sidecar 不是 application validator 可消费的正式 manifest。应由父级显式集成窄 candidate API，并继续现有 source hashes、occurrence/edition/citation、HMAC/cache scope、质量闸门及 needs_review 约束；**不批量把 needs_review 改 extracted/approved**。
4. 如要精确文档页 bbox，父方须先证明 source raster 在该特定 page occurrence 中的放置变换，包括 crop/scale/旋转/坐标单位；本次 `p0001.png` 文件名不构成 page-placement 证据。没有证据就保持 spatial-parent-only，不补造引用。
5. 表格/图示线性文字即使通过闸门也继续结构未验证。单元格拓扑、层级、图边关系、整文阅读另验，不用文字一致率充当语义通过。
6. **仍需父会话完成真实 GPU / UID999 受限 worker 接入与端到端验收**：新客户端实际模型 raw response/finish/usage、同输入独立 OCR、未决行传播、bundle/app 接受/拒绝、限制环境依赖与已有 worker cleanup/teaching return。这里没有进行任何这些接入/部署操作，也没有宣称所有上传资料识读目标完成。

## 已知限制

- 只覆盖留存 p1/p9 的文字 evidence；无整语料批准或模型效果推广。
- group 大小有明确上限，超过范围不会猜合并；未匹配仍保留。
- 只有历史 case 的真实 finish 元数据，没有其原始 HTTP wire；已如实标注。
- 文档页定位、图表结构、真实 GPU/UID999 接入尚未验证；这是范围内预期留给父集成的工作，不是通过 fixture 代替验收。
