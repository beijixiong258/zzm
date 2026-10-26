# AIcademiya

面向教师备课和学生学习的自用项目，以课程、教学任务和学习记录为主线。教师通过对话配置课程与任务，文件管理保留独立页面；学生阅读材料、作答、提交附件并与 AI 对话。目前打通教学链路，不设计评分和评级。

当前版本为 **0.1.0**。技术栈为 **Vue 3 + TypeScript + Vite、Java 17 + Spring Boot + Spring AI + MyBatis-Plus、MySQL**。本文件统一维护使用、运行与协作说明。

## 日常使用

1. 打开 [本机入口](http://127.0.0.1:5173)，选择教师、学生或管理员。默认关闭演示模式；空数据库先选择管理员，创建首位管理员。启动不会清空已有账号或课程。
2. 教师在课程对话中说明课程名称、学生情况和教学要求，由 AI 配置基本字段。课程对话也可创建任务、邀请学生和查看课程情况；字段保存结果以业务接口实际返回为准。
3. 在任务对话中配置任务名称、类型、教学语言、学习目标和补充要求。上传文件或文件夹时，可选择“师生均可见”或“仅教师与 AI 可用”；可见性在文件入队时固定。
4. “选择文件”打开课程已有材料的独立选择面板，保留文件夹、解析状态、预览和多选。“保存”只确认本轮材料选择，不要求任务名称、不创建或保存任务、不调用 AI；取消和返回不提交本轮选择。切换面板保留任务内容、上传队列与进度，新上传材料自动选中。
5. 任务材料与题目导入来源分别选择。导入保留题干、顺序和材料引用；开放题有原文参考答案就使用，没有则留空，由 AI 判断学生回答质量，不要求选项或选项答案匹配。选择题仍需通过必要校验。
6. 生成或修订后，教师检查讲义、题目及参考答案，再进行学生预览和发布。草稿修改不会覆盖已发布版本，学生记录绑定实际学习的版本。
7. 学生用用户名及个人邀请码，或邮箱密码登录；加入课程的口令与个人登录邀请码用途不同。学生可以阅读、作答、上传附件、与 AI 对话并导出自己的学习结果。
8. 教师可在任务对话中查看学生进展、学习记录和待审核反馈，确认完成或要求修改。AI 反馈支持立即显示或经教师审核后显示，不自动形成正式成绩。

教师对话记录和未发送消息保存在当前浏览器，不跨设备同步。界面提供简体中文、英文；教学语言独立于界面语言。

## 文件管理与 AI 输入

课程文件管理支持修改名称、可见性、重新解析、归档和逐个删除。

- **归档**：隐藏材料，不再供新任务选择，原文件和已有引用保留；勾选“显示已归档项目”可恢复。
- **删除**：解除使用关系后，将未被引用的上传副本移入回收目录。仍被任务或发布版本引用的材料不能直接删除。本机原始材料不受影响。
- 支持 PDF、Word、PowerPoint、Excel、EPUB、文本及图片，单文件最多 **25 MiB**。默认处理范围为 **300 个单元、300,000 个字符**。前端最多同时上传 3 个文件，后端并行处理 2 份材料。
- PDF 全部页面都有完整可用文字层时本地提取文字；需要保留图像或无法可靠提取时，整份 PDF 按原页序准备页面图片。PDF 准备不做 OCR、不调用模型转录；不为降低估算而漏页或截断内容。
- 处理中、解析失败或内容不完整的材料不能用于生成或发布；“处理完成，估算偏高”仍是可用材料。

模型上下文参考值为 **256,000 token**，输入提醒线为 **200,000 token**。所有本地 token 计算仅供参考，超过提醒线只提示；实际容量、用量及请求能否接受，以上游服务商反馈为准。请求完整发送材料和当前对话，`max_tokens` 按模型配置发送，不由本地固定窗口倒推压缩。未配置时，生成默认 16,000，对话默认 4,096。

成功响应显示上游实际 usage；材料提取失败、模型输出不合法、题目校验失败及上游请求失败分别报告。上游 HTTP 429 与本地并发繁忙分开显示，不把中断或截断输出当作成功结果。现有并发、文件大小、消息数量和材料完整性限制继续生效；开始新对话不会删除旧学习记录。

## Windows 运行

本机开发需要 PowerShell 7、JDK 17、Maven、Node.js 和 MySQL。IDE 项目 SDK、Maven 使用的 JDK、`JAVA_HOME` 均设为 Java 17。使用默认直连网络。

首次准备前端依赖：

```powershell
Set-Location -LiteralPath 'C:\Users\user\Desktop\zzm\app'
pwsh.exe -File .\setup.ps1
```

分别在两个 PowerShell 7 窗口启动后端和前端：

```powershell
pwsh.exe -File 'C:\Users\user\Desktop\zzm\app\start.ps1' -Component backend
pwsh.exe -File 'C:\Users\user\Desktop\zzm\app\start.ps1' -Component frontend
```

前端地址为 `http://127.0.0.1:5173`，后端 API 为 `http://127.0.0.1:8001/api`。开发前端直接请求后端，不经过开发代理。

也可使用项目现有 Docker Compose 配置：

```powershell
pwsh.exe -File 'C:\Users\user\Desktop\zzm\app\start.ps1' -Component docker
```

该命令构建并启动 MySQL、后端和前端。Compose 映射数据库端口为 3306；现有本机 Java 配置连接 3307，两者按各自运行方式使用。不要在已有服务占用端口时重复启动另一套服务。

前端类型检查与生产构建使用现有命令：

```powershell
npm.cmd --prefix .\app\frontend run build
```

该命令依次执行 `vue-tsc --noEmit` 和 `vite build`，输出到 `app/frontend/dist`。生成后可用 `node.exe .\app\frontend\static-server.mjs` 启动静态服务。源码改动不会自动替换已运行容器中的构建产物。

## 本机配置

| 配置                       | 位置与用途                                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| MySQL 地址、账号和明文密码 | `app/server/src/main/resources/application.yaml` 的 `spring.datasource`                                    |
| Docker MySQL 初始化密码    | 同一 YAML 中的 `mysql.root-password`；启动脚本读取，不写入 `.env`，不更改已有库密码                        |
| 硅基流动配置               | `app/.env` 中的 `AICADEMIYA_AI_API_KEY`、`AICADEMIYA_AI_BASE_URL`、`AICADEMIYA_AI_MODEL`，启动脚本自动加载 |
| 模型其他参数               | `app/config.json` 的 `ai` 节；非空 AI 环境变量优先。可用 `AICADEMIYA_CONFIG` 指定配置路径                  |
| 上传目录                   | `AICADEMIYA_UPLOAD_DIR`，本机默认 `app/data-local/uploads`                                                 |
| 文件回收目录               | `AICADEMIYA_TRASH_DIR`，本机默认用户桌面的 `智能体回收站/垃圾桶/AIcademiya`                                |
| 演示数据                   | `AICADEMIYA_DEMO_ENABLED` 默认 `false`，启动脚本同样默认关闭                                               |

`setup.ps1` 只在 `config.json` 不存在时从 `config.defaults.json` 初始化配置，不覆盖已有配置。Java 业务配置以 `application.yaml` 和 `AppProperties` 为准；默认 JSON 中保留的旧 Python 参数不参与当前业务链路。

## 目录

```text
zzm/
├─ README.md
├─ app/
│  ├─ frontend/
│  │  ├─ src/
│  │  │  ├─ App.vue、main.ts          应用入口、登录及页面切换
│  │  │  ├─ views/                  教师对话、任务编辑、学生学习、文件管理
│  │  │  ├─ components/             对话、弹窗、上传、材料树、讲义等复用组件
│  │  │  ├─ classroom-state.ts      当前用户、课程和页面状态
│  │  │  ├─ classroom-api.ts        接口类型及请求
│  │  │  ├─ useCourseMaterials.ts   材料加载与处理状态轮询
│  │  │  ├─ i18n.ts、locales/       中英界面文案
│  │  │  └─ classroom.css、design-tokens.css
│  │  ├─ public/                   正式静态资源
│  │  ├─ tests/brand-assets.mjs     图标生成工具，由 build:brand 调用
│  │  └─ Dockerfile、static-server.mjs、构建配置
│  ├─ server/                      Java 17 后端及 application.yaml
│  ├─ tools/                       独立维护工具
│  └─ start.*、setup.*、compose.yaml、Dockerfile、配置文件
└─ 测试用材料不要删/                用户原始材料
```

`app/tools/export_legacy.py` 是独立的旧 SQLite 数据导出工具，使用 Python 标准库，不依赖已移出的历史后端。指定 `--database`、`--output`，必要时传入 `--catalog`；导入仅面向空的 MySQL 应用库，日常启动不运行迁移。

`app/tools/Recycle-OrphanUploads.ps1` 用于核对无数据库引用的上传文件，默认只列出结果；显式传入 `-Apply` 才移入垃圾桶。它使用 MySQL ODBC 驱动及当前 PowerShell 会话的数据库参数，执行前按实际数据库和上传目录设置。维护工具不在应用请求链路内。

## 协作约定

- 只处理当前任务直接相关的源码与状态，保留已有工作区改动。前端按实际调用关系复用，避免重复校验、无调用方的兼容分支和无价值的抽象；不附加安全设计或依赖升级。
- Java 固定使用 17。MyBatis-Plus 保留 `IService`、`ServiceImpl`、`BaseMapper`，查询更新优先使用 Lambda 条件构造器，同一实体业务集中在对应 Service。遵循 Spring AI 官方接口，不增加零散的小包和小类。
- 材料状态归 `MaterialService`，格式解析归 `DocumentParser`，AI 提示与结果归 `AiService`，模型协议、重试及响应完整性归 `QwenClient`，后台调度入口为 `BackgroundJobs`。
- Java 类名用大驼峰，字段、方法及 JSON 用小驼峰，数据库字段用下划线；沿用 Lombok、Hutool JSON。
- 保持材料选择、题目导入来源、预览状态独立。保持已发布版本不可变，学习记录绑定明确版本；学生页面与教师学生预览均用公开内容投影，内部提示、参考答案和未审核反馈不展示给学生。
- Windows 操作使用 PowerShell 7，不启动代理。核对 AI 配置以实际进程、容器挂载和环境变量为准，不用空配置覆盖现有配置，不在输出中展示密钥。
- 编译、测试、启动以当次授权为准，不新增测试类或测试脚本，不运行无关的全量检查。临时启动的检查服务在检查后停止，用户要求保留的服务及原有服务除外。
- 不自行修改版本号，不提交、推送 Git 或创建 PR。原课程材料、数据库和本机配置只按明确任务处理。
- 删除、清理统一移入 `C:\Users\user\Desktop\智能体回收站\垃圾桶`，不永久删除、不清空垃圾桶，不另外创建备份。
- 文档集中维护本 README，不保留历史验证流水，不再另建 docs 目录或交付报告。完成后交付实际改动、执行结果和未验证项，等待用户手动验收。
