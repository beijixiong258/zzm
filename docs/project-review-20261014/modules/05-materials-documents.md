# 05 · 材料库、完整文档与 Worksheet 导入

## 作用

这个模块把教师提供的文件变成可复用、可校订、可引用的教学来源。它连接文件上传、课程材料库、课次关联、完整文档阅读和题目编辑。

教师入口是 Course materials、Session Materials、Read complete document 和 Questions & answers。学生通过已发布课程读取获准材料与题图。

## 源码分工

| 源码 | 职责 |
|---|---|
| `backend/aicademiya/material_library.py:9–87` | 一个课程文件对应一个 Material ID；`material_courses`确定课程归属，`session_materials`记录课次关联 |
| `materials.py` / `material_extraction.py:486起` | 25MiB轻量提取入口；原生文字、CPU OCR、覆盖统计和失败说明 |
| `material_security.py` / `extraction_limits.py` | 上传容器、实际解压量和像素规模检查 |
| `link_materials.py:30–101` | URL/DOI格式、公共地址和DNS绑定；防止资料链接访问内网 |
| `document_bundle.py:246–401` | 完整bundle、来源SHA、页/块/图片资源与格式校验 |
| `document_jobs.py:34–200` | 单串行队列、工作器子进程、失败恢复、验证后提交 |
| `document_storage.py:25–89` | 任务表、不可变revision、选定edition的manifest读取 |
| `document_api.py:88–175` | 能力、任务回执、文档摘要、补充说明和鉴权页读接口 |
| `document_supplements.py` | Office讲者备注、Word说明与Excel评论索引 |
| `worksheet_import.py` / `worksheet_materials.py:154起` | 文本/图题识别、复用原Material、审核后提交 |
| `tools/document_stage12/` | SSH传输、工作器监督、租约和基础PDF解析 |
| `tools/material_stage13/` | 多格式原生读取、Office受控转换和prepared bundle |
| `tools/material_stage15/` | 页级Markdown/原图适配和来源谱系 |
| `tools/material_stage16/` | XLS/XLSX账本、旧Office容器、Excel评论 |

工具目录名代表形成阶段。Stage12/13/15的文件仍进入Stage16运行包，属于当前依赖。

## 数据流

### 上传与共享

1. 前端冻结每个文件的type、visibility、processing mode，XHR报告实际发送字节。
2. 后端保留原件，创建Material，并进入课程库及当前课次关联。
3. 轻量模式生成有限excerpt/CPU OCR报告；完整模式进入durable document job。
4. 从课次移出只删除关联。其他课次、课程库和已发布edition继续引用同一文件。
5. 编辑材料属性或校订来源改变草稿，发布新edition后学生才使用新内容。

### 完整处理

`DocumentQueue → document_ssh_bridge → Ubuntu受限工作器 → 原生准备 → 按需GPU页处理 → bundle校验 → document_revisions → Material草稿绑定`。

原生文字、原图、转写和原始回执一并保留。CPU能完成的内容先处理；视觉工作通过既有独占租约使用T10-B。工作器清理并释放资源后归还教学副本。当前应用单worker，任务失败由教师明确重试。

文档API将私有文件根目录转换成鉴权资源URL；访问同时绑定Material、revision和edition。源块校订产生新revision，旧edition保持原绑定。

### Worksheet复用

教师选已有Worksheet及可选teacher-only Answer key。`worksheet_materials.binding`绑定原件SHA和内容revision，路径迁移不改变语义绑定。模型提取题干、选项和所供答案，随后生成教师可编辑预览；commit重新检查来源和权限，沿用原Material ID。

`recognize:110–150`检查提议答案是否出现在来源中，并在缺少明确答案源时留空。答案和题目的语义对应由模型及教师复核共同完成；文字出现检查只负责限制答案来源。

## 格式与状态

- 完整处理：64MiB、1000页/帧；轻量预览：25MiB。
- PDF/Office/图片/文本有不同原生、转换和视觉处理路径。
- XLSX读取全部实际存储cell与sheet，区分公式原文和缓存值；预览为单元格账本和原始媒体。
- XLS的XLSX表示由LibreOffice转换得到，保存原始XLS身份与转换记录。
- `document_jobs`：queued/running/completed/failed；`document_revisions`：不可变manifest和来源校订谱系。
- Office备注和评论默认私有，分享需要显式操作。

## 当前证据

本轮读取上述接口、存储、队列、Worksheet和格式转换主链；相关测试入口见 `backend/tests/test_stage16_*` 以及Stage12–15文档测试。实际测试结果统一放在上层 `verification.md`。

远端现有13个任务中9个完成、4个失败，9个revision。当前队列没有queued/running任务。Stage16历史真实DOC/PPT/XLS/XLSX验收见 `app/DEPLOYMENT_STAGE16_RESULT.md`；本轮远端采用只读核验。

## 整理结论

- **P1：保护被引用资源。** 本轮生产材料中13份原件仍位于20261006旧release。释放旧目录前要同时查当前材料、immutable snapshot和pending import绑定。
- **P2：降低入口复杂度。** 当前代码按历轮Stage分布，运行依赖应由发布allowlist和本报告定位，不能按目录年龄清理。
- **P2：保持Worksheet复核。** 现有来源过滤约束答案文本；复杂分组与图题的对应继续通过review确认。

已清理本地历史OCR候选模型、依赖下载和实验venv，保留解析结果、原始回执、review页面、原件、manifest和当前应用依赖。
