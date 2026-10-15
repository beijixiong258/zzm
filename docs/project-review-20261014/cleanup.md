# 清理与恢复记录

## 已完成

从活跃项目移出 **13个目标、28,694个文件、7,791,029,093字节（7.79GB）**，全部进入D盘系统回收站。确认可重建的下载和实验环境按用户授权免另做备份。

回收前检查了完整目标边界、链接/长路径、当前进程引用和回收站容量；既有回收载荷约10.67GB，配置容量约88.41GB，整批容量充足。回收后逐个找到精确$I原路径与$R载荷，并校验所有文件SHA/目录结构。D盘小样使用原生Restore还原且字节一致。

回收站仍占用同卷磁盘；本轮缩小的是项目活跃目录。保留回收站可由用户恢复。

## 回收清单

| 相对项目根路径 | 文件数 | MB（十进制） |
|---|---:|---:|
| `app/artifacts/ocr-stage1/models/minicpm-v4.5/MiniCPM-V-4_5-Q4_K_M.gguf.part` | 1 | 1740.64 |
| `app/artifacts/ocr-stage1/models/minicpm-v4.5/mmproj-model-f16.gguf.part` | 1 | 780.14 |
| `app/artifacts/ocr-stage1/models/paddleocr-vl1.6/PaddleOCR-VL-1.6-GGUF.gguf` | 1 | 935.77 |
| `app/artifacts/ocr-stage1/models/paddleocr-vl1.6/PaddleOCR-VL-1.6-GGUF-mmproj.gguf` | 1 | 881.77 |
| `app/artifacts/ocr-stage1/downloads` | 2 | 656.68 |
| `app/artifacts/ocr-stage1/linux-wheels` | 116 | 556.05 |
| `app/artifacts/ocr-stage1/linux-wheels.tar` | 1 | 556.29 |
| `app/artifacts/document-pilot/linux-wheels` | 118 | 246.50 |
| `app/artifacts/document-pilot/wheels-delta.tar` | 1 | 169.00 |
| `app/artifacts/document-pilot/mineru-4.0.11-py3-none-any.whl` | 1 | 3.66 |
| `app/.venv-ocr-stage1` | 25309 | 972.25 |
| `app/artifacts/magicschool-session4/browser-profile` | 1570 | 144.50 |
| `app/artifacts/magicschool-session5/browser-profile` | 1572 | 147.79 |

模型与projector来源URL/revision/期望SHA保留在 `app/artifacts/ocr-stage1/download-manifest.json`；wheel版本和SHA保留原manifest以及本轮cleanup-plan。实验Python环境包版本另存 `evidence/ocr-experiment-package-versions.json`。唯一实验结果、失败回执、原图和review页面原位保留。

## 文档整理

已备份并更新7份入口文档：根README、app README、AGENTS、BUILD_CHECKPOINT、CONTRACT、DEPLOYMENT和sample_data README。原版zip逐文件SHA核验完成：

- `evidence/entry-documents-before.zip`
- `evidence/entry-documents-backup.json`

新增 `app/DOCUMENTATION.md` 区分当前契约和历史/补充记录。历史Stage文件保留原路径，兼容代码和历轮证据链接。

## 明确保留

- 课堂原件、网页旁_files、research来源和课堂身份记录。
- 当前backend/frontend源码、tools、app/.venv、frontend/node_modules与dist。
- local-settings、旧app/data、private_seed和所有现存数据库/上传。
- 独有模型原始响应、OCR/图文bundle、失败日志、review素材、发布manifest与恢复证据。
- 生产服务器所有运行文件、旧release和配置。现有13份原件仍引用20261006旧release。
- 本机Linux实验venv及旧候选extract树：含reparse或不可读条目，保留供后续确权。

首轮库存记录90,599个可读取普通文件，共13.65GB；跳过219个reparse条目，另有234项读取错误。详细范围见inventory-before，本轮清理数量来自已成功核验的独立清单。

## 清理后库存

同一不跟随reparse的盘点口径下，活跃项目可读取普通文件体积从13.65GB降至5.89GB，包含本轮新增报告、库存、测试XML与复现证据。219个reparse和234个读取错误原位保留，未改变。清理后134个运行包输入仍与生产发布对应，当前app/.venv、frontend/node_modules/dist、旧data、配置与sample_data全部存在。

## 恢复

打开Windows回收站，按原路径找到对应目标并选择“还原”。精确$I/$R载荷路径、理由和字节证据存放在 `evidence/cleanup-result.json`。7份文档原版可从entry-documents-before.zip解压回原相对路径。

`tools/recycle_disposable.py`记录本轮允许目标和核验步骤。目标已完成回收，无需重复运行execute。
