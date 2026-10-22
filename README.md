# AIcademiya

课程与 AI 学习任务管理。开发分支为 `cys`，界面默认中文，可切换 English。应用版本沿用 0.1.0。

Vue 3 前端使用 **5173**；Spring Boot、Spring AI、MyBatis-Plus 后端使用 **8001**。数据库使用 MySQL，材料保存在本地持久存储。文件解析与业务后端一同运行，模型调用沿用硅基流动配置。

## 本机开发

需要 JDK 21、Maven、Node.js 和 MySQL。进入 `app` 后运行 `pwsh.exe -File .\setup.ps1` 准备前端依赖和本地配置。AI 配置继续读取不进入 Git 的 `app/config.json`，也可通过 `AICADEMIYA_AI_API_KEY`、`AICADEMIYA_AI_BASE_URL`、`AICADEMIYA_AI_MODEL` 覆盖；材料视觉识别需要支持图像输入的模型。

创建 MySQL 数据库 `aicademiya` 和对应用户，通过 `MYSQL_URL`、`MYSQL_USER`、`MYSQL_PASSWORD` 配置连接。分别运行：

```powershell
pwsh.exe -File .\start.ps1 -Component backend
pwsh.exe -File .\start.ps1 -Component frontend
```

打开 http://localhost:5173。全新数据库首次使用时创建管理员账号。已有开发库如缺少 `course_material.extraction_report_json`，需补充可空的 JSON 列；新数据库自动建表。

## 文件处理

支持 PDF、DOC/DOCX、PPT/PPTX、XLS/XLSX、TXT/Markdown、PNG/JPEG/WebP，单文件最大 25 MiB。PDFBox 读取 PDF 文本并按需逐页渲染；POI 读取 Office 正文、表格、公式和图片。扫描页、图示及课件页面作为图像交给千问识别，原文件保留供核对。

解析报告记录总单元数、完成数、AI 识别数、失败位置和截断情况。默认最多处理 300 个单元、保留 300000 个字符；可通过 `AICADEMIYA_DOCUMENT_MAX_UNITS`、`AICADEMIYA_DOCUMENT_MAX_CHARACTERS` 调整处理范围。超限或读取失败时保留可读内容供预览，材料完整处理后才能生成或发布任务。旧材料可在材料库点击“重新解析”。Office 版式、字体和特殊嵌入对象需对照原件核验，无法解析的内容可导出为 PDF 后上传。

千问请求对连接失败、429 和服务端错误最多尝试三次；输出截断或识别不完整会记为失败。连续三个处理单元失败时停止当前材料，保留报告供重试。重启后，未完成的材料处理重新排队。

## Docker

进入 `app`，将 `.env.example` 复制为 `.env` 并填写数据库密码，确认 `config.json` 存在，然后运行：

```powershell
docker compose up -d --build
```

Compose 启动 MySQL、后端和前端，持久保存数据库及上传文件。后端镜像包含文档渲染所需的中文字体。浏览器直接访问 8001，后端允许本机 5173 的跨域请求；接入域名或 HTTPS 时再调整允许来源和 Cookie 配置。

## 可选的旧数据导入

Python 仅用于旧 SQLite 数据的只读导出，当前应用运行不需要 Python。导出目录必须尚不存在：

```powershell
python .\tools\export_legacy.py --database .\data-local\aicademiya.sqlite3 --output .\legacy-export
```

导出包含原文件副本和 `manifest.json`。首次启动 Java 后端前，将 `AICADEMIYA_LEGACY_IMPORT` 指向导出目录的绝对路径；导入要求空的 MySQL 应用数据库，完成后移除该环境变量。原数据库不修改，旧 Python 后端源码仅保留作迁移参考。

源码入口与约定见 [app/AGENTS.md](app/AGENTS.md)。
