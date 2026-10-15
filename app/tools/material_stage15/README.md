# Stage15 本地图文资料页适配器

零推理、零网络的 CPU 库与 CLI：消费已完成的 `body_text / images / uncertainty` 响应，生成 schema1 页面、Markdown 字段、完整源图、真实源像素裁图和程序生成的来源绑定。只新增本目录及 `artifacts/stage15/material-adapter/`。

## 接口

```python
from tools.material_stage15 import CropPolicy, plan_page, adapt_page, write_image_bundle, verify_readback
from tools.material_stage15.prepared import augment_prepared_bundle

plan_page(response: dict, *, width: int, height: int,
          page_number: int = 1, printed_label: str | None = None,
          body_format: str = 'markdown', policy: CropPolicy = CropPolicy(),
          start_index: int = 0) -> dict

adapt_page(raster: Path | str, response: dict, bundle_root: Path | str, *,
           expected_raster_sha256: str, source_mapping: dict | None = None,
           page_number: int = 1, printed_label: str | None = None,
           body_format: str = 'markdown', policy: CropPolicy = CropPolicy(),
           start_index: int = 0, response_file: Path | str | None = None) -> dict

write_image_bundle(raster: Path | str, response: dict, output: Path | str, *,
                   expected_raster_sha256: str, source_mapping: dict | None = None,
                   response_file: Path | str | None = None,
                   body_format: str = 'markdown', policy: CropPolicy = CropPolicy()) -> dict

augment_prepared_bundle(prepared_root: Path | str, output: Path | str,
                        page_inputs: list[dict], *, body_format: str = 'markdown',
                        policy: CropPolicy = CropPolicy()) -> dict

verify_readback(bundle_root: Path | str) -> dict
```

- `plan_page` 是纯函数，返回 `page / regions / protocol / finish / crop_policy`。
- `adapt_page` 返回普通 schema1 Page，并写入 `pages/`、`assets/`、`raw/`。输入必须是已准备好的单帧 PNG；不另做透明图、动画、Office 转换流程。
- `response` 是原始 OpenAI completion 对象，或旧实验的 `content + finish_reason + usage` case。仅接受完整 JSON 与 `finish_reason=stop`，不从模型生成页号/ID。
- 有原始响应文件时传 `response_file`，保存其**字节原样**；仅传对象时保存对象 JSON，不能声称字节级保留了不存在的原始文件。
- 编号从 `pN-bI` 顺序生成；正文、全源图和候选区域都保留 required block/page 字段。路径是程序生成的相对 POSIX 路径。
- 页面 `image` 和全源 image block 永远存在。即使 `images=[]`，成功转写也不会删除源图。
- 正文原样放在 `text`，默认 `text_format=markdown`；不改数字、符号、角色箭头、空白/填空，不把 tab 文字自动编成表格。`body_format=plain` 可保留旧接口含义。
- image block 固定 `type=image / text='' / quality=extracted`。描述只在可选 `visual_description` 与 raw 派生 metadata 中；不能成为教材原文引用。
- 正文为 `extracted`，issues 明示 machine-extracted / not-independently-verified。父集成0.1.1依据新真实输出修正了非空uncertainty整页拒读：未定位的模型说明保存在raw及`model_uncertainty:`提示，页面显示needs_review，但不据此判全部正文不可用；真实回复`无`等显式空值仍原样留raw。正常正文及源像素均可读取；没有伪造局部坐标或独立验证。
- 不输出 `approved`、教师 review、独立 OCR 验证或模型问答成功。

## 裁框与来源

默认策略：向外扩 12 个真实源像素，距源边缘不超过 24 像素时向外贴边；限制在实际图像边界内。先 `floor` 左上、`ceil` 右下，确保候选区域被包含。raw 同时记录模型原始 0..1000 坐标、原候选像素框、最终像素框、调整原因；block bbox 使用最终真实像素框归一化到 0..1。

只合并**原始候选坐标完全相同**的框，保留所有原候选编号、描述。全源候选复用 mandatory 全源图。不同坐标的重叠框不裁切、分割或猜关系，保持各自区域并记录 overlap。padding 可能包含少量相邻画面，这是明确的上下文保留策略。

**完整题图必须选全源块**：候选区域只是定位辅助，不足以断言包含全部说明、空格、选项、连线或选词盒。全源图逐字节保留；预处理不解题。

`source_mapping` 的典型形式：

```json
{
  "kind": "recorded_source_page",
  "source_sha256": "<verified original hash>",
  "source_format": "pdf",
  "page_number": 8,
  "page_number_kind": "original_pdf_physical",
  "raster_page_bbox": [0.0, 0.0, 0.519500..., 1.0],
  "evidence": ["recorded manifest path"]
}
```

`raster_page_bbox` 是实际输入 raster 在原页／已记录 Office 渲染页中的范围。程序把区域坐标映回这个外框；没有完整几何链则 `source_page_bbox=null`，明确 `standalone_image_source`。该 mapping 由调用方提供的已有证据决定，不由模型推断。Office 页号明确标为 `derived_office_rendered_page`，不冒充原生 PDF 页号。

独立 PNG CLI 的 bundle 原件是 PNG、`source_format=png / page_count=1`，SHA 绑定 PNG。原教材文件 SHA 与真实页映射只作为 raw 补充来源。`preview.pdf` 复用现有 `simple_material.image_pdf` 生成，明确是派生预览。

对完整 prepared bundle，`augment_prepared_bundle` 在**新目录**复制后追加块，保留原 source SHA、原页号、原文、其他页面、preview、supplements；历史 manifest 存入 raw。`page_inputs` 示例见实际交接目录的 `prepared-page-inputs.json`。追加的 VLM 正文可能与 native 正文重复，父会话 reader 需按来源类别选择，不能据此重复累计内容覆盖。

## CLI 与测试

在 `D:/HermesProjects/EDUC7703/app` 下，用项目 venv；不启动服务器、GPU 或模型。

```bash
# 新输出目录必须不存在。
PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m tools.material_stage15 consume \
  --experiment 'C:/Users/17193/Desktop/AIcademiya-27B图文实测-20261012-113346/minimal-final' \
  --output artifacts/stage15/material-adapter/real10-new

PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m tools.material_stage15 image \
  --input ACTUAL.png --response ACTUAL-response.json --sha256 ACTUAL_SHA256 \
  --output artifacts/stage15/material-adapter/one-new

PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m tools.material_stage15 verify \
  --bundle artifacts/stage15/material-adapter/real10/bundles/05-sample23

PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m tools.material_stage15 prepared \
  --input FULL_PREPARED_BUNDLE --pages PAGE_INPUTS.json \
  --output artifacts/stage15/material-adapter/prepared-new

# 首次运行前创建 XML 与保留测试 fixture 的父目录。
./.venv/Scripts/python.exe -c "from pathlib import Path; Path('artifacts/stage15/material-adapter/tests').mkdir(parents=True,exist_ok=True)"
PYTHONDONTWRITEBYTECODE=1 ./.venv/Scripts/python.exe -m pytest \
  tools/material_stage15/tests -q -p no:cacheprovider \
  --basetemp=artifacts/stage15/material-adapter/tests/retained-fixtures-new \
  --junitxml=artifacts/stage15/material-adapter/tests/adapter-tests-new.xml
```

`verify_readback` 回读 manifest/raw/响应/全源图/每个 asset：SHA、block 绑定、bbox、尺寸、mode、源像素 bytes 一致，正文与实际原始响应的字符串一致。其结果是**适配器保真证据**，不是模型语义或 OCR 准确率。

## 本次实际验收

- 27 个聚焦 tests 通过，exit0；XML：`artifacts/stage15/material-adapter/tests/adapter-tests-pass.xml`。包括 parent 最新 plain 规范化省略、None description 省略及 description 2000字符上限。
- 实际10图消费 exit0；10/10 parser validator、10/10 当前严格 application validator、10/10 独立回读通过。
- 19 原候选；10 mandatory 全源资产 + 17 区域资产 = 27 源图资产；2 个整页候选复用全源图。
- 36 blocks、13,503 正文 Unicode 字符，正文原字符串保留；实际 uncertainty 均空，0 needs_review **不等于准确率已通过**。
- 9 个有记录的原文件／渲染页关联与源文件 SHA 核对；diagram 输入的源 PNG 裁剪/2x 变换链保留，但原 PDF 页几何未完整确认，作为独立图片源处理。
- 当前父会话的 optional fields 已能通过 strict app 校验，本子任务未改 backend。应用字段若在其他旧 checkout 尚未集成，CLI 会保留 parser 校验结果并明确报告 `text_format / visual_description` 未识别，不删字段伪造兼容成功。
- **真实输出没有 Markdown 表格**。仅给文字加 Markdown 格式标签，不是完成了新表格转写验收。Markdown 表格/箭头/空格字面保持测试使用明示 synthetic protocol fixture，未混入10图模型结果。

实际 prepared 合并尝试 exit1：旧 `r6-final-inputs/readback/mask-bundle` 是缺33个引用 asset 的稀疏回读，并非完整 prepared bundle；输入校验在复制前拒绝，未创建新输出。未补造 asset、删块或修改旧快照。prepared 组合功能已用明确标记的两页 fixture 测试，真实完整 prepared 合并仍待补测。

交接详情和剩余工作：`artifacts/stage15/material-adapter/HANDOFF.md`。主要证据：`real10/summary.json`、`real10/source-hashes.json`、`readback-all10.json`、`verification.json`、`real10/index.html`。
