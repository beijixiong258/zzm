# AIcademiya

面向教师备课和学生学习的自用项目，以课程、教学任务和学习记录为主线。教师通过对话配置课程与任务，文件管理保留独立页面；学生阅读材料、作答、提交附件并与 AI 对话。目前打通教学链路，不设计评分和评级。

当前版本为 **0.1.0**。技术栈为 **Vue 3 + TypeScript + Vite、Java 17 + Spring Boot + Spring AI + MyBatis-Plus、MySQL**；前端组件统一采用腾讯 **TDesign Vue Next**。本文件统一维护使用、运行与协作说明。

## 日常使用

1. 打开 [本机入口](http://127.0.0.1:5173)，选择教师、学生或管理员。默认关闭演示模式；空数据库先选择管理员，创建首位管理员。启动不会清空已有账号或课程。
2. 教师在课程对话中说明课程名称、学生情况和教学要求，由 AI 配置基本字段；也可在“当前课程配置”中直接编辑并保存课程名称、代码、课程信息、学生情况和课程通用指令。表单底部只保留保存操作，课程标题右侧提供“新建任务对话”和“文件管理”；先保存课程配置，才能新建任务对话，有未保存修改时须先保存。课程对话也可邀请学生和查看课程情况；字段保存结果以业务接口实际返回为准。
3. 在任务对话中配置任务名称、类型、教学语言、学习目标和补充要求，也可在“当前任务配置”中直接编辑这些字段，在配置框右下角保存草稿；新任务无需先通过 AI 命名。生成讲义、导入已有作业、学生预览和发布位于任务标题右侧，修订、学生进展等入口归入“更多操作”。上传文件或文件夹时，可选择“师生均可见”或“仅教师与 AI 可用”；可见性在文件入队时固定。
4. 上传和附件区域位于“当前任务配置”卡片顶部，聊天输入框保留在下方。上传只将文件加入课程文件库；通过“文件管理”进入任务内的附件选择面板，保留文件夹、解析状态、预览和多选，手动勾选后点击“保存”才加入本任务。“保存”只确认本轮附件选择，不要求任务名称、不创建或保存任务、不调用 AI；取消和返回不提交本轮选择。切换面板保留任务内容、上传队列与进度，新上传材料不会自动选中。
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
Set-Location -LiteralPath 'C:\Users\user\Desktop\zzm'
pwsh.exe -File .\setup.ps1
```

分别在两个 PowerShell 7 窗口启动后端和前端：

```powershell
pwsh.exe -File 'C:\Users\user\Desktop\zzm\start.ps1' -Component backend
pwsh.exe -File 'C:\Users\user\Desktop\zzm\start.ps1' -Component frontend
```

前端地址为 `http://127.0.0.1:5173`，后端 API 为 `http://127.0.0.1:8001/api`。开发前端直接请求后端，不经过开发代理。

也可使用项目现有 Docker Compose 配置：

```powershell
pwsh.exe -File 'C:\Users\user\Desktop\zzm\start.ps1' -Component docker
```

该命令构建并启动 MySQL、后端和前端。Compose 项目名沿用原来的 `app`，目录迁移不改变原有 Compose 数据卷名称。Compose 映射数据库端口为 3306；现有本机 Java 配置连接 3307，两者按各自运行方式使用。不要在已有服务占用端口时重复启动另一套服务。

前端类型检查与生产构建使用现有命令：

```powershell
npm.cmd --prefix .\frontend run build
```

该命令依次执行 `vue-tsc --noEmit` 和 `vite build`，输出到 `frontend/dist`。生成后可用 `node.exe .\frontend\static-server.mjs` 启动静态服务。源码改动不会自动替换已运行容器中的构建产物。

## 本机配置

| 配置                       | 位置与用途                                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| MySQL 地址、账号和明文密码 | `src/main/resources/application.yaml` 的 `spring.datasource`                                    |
| Docker MySQL 初始化密码    | 同一 YAML 中的 `mysql.root-password`；启动脚本读取，不写入 `.env`，不更改已有库密码                        |
| 硅基流动配置               | `.env` 中的 `AICADEMIYA_AI_API_KEY`、`AICADEMIYA_AI_BASE_URL`、`AICADEMIYA_AI_MODEL`，启动脚本自动加载 |
| 模型其他参数               | `config.json` 的 `ai` 节；非空 AI 环境变量优先。可用 `AICADEMIYA_CONFIG` 指定配置路径                  |
| 上传目录                   | `AICADEMIYA_UPLOAD_DIR`，本机默认 `data-local/uploads`                                                 |
| 文件回收目录               | `AICADEMIYA_TRASH_DIR`，本机默认用户桌面的 `智能体回收站/垃圾桶/AIcademiya`                                |
| 演示数据                   | `AICADEMIYA_DEMO_ENABLED` 默认 `false`，启动脚本同样默认关闭                                               |

`setup.ps1` 只在 `config.json` 不存在时从 `config.defaults.json` 初始化配置，不覆盖已有配置。Java 业务配置以 `src/main/resources/application.yaml` 和 `AppProperties` 为准，模型模块读取 JSON 中的 `ai` 节。

## 目录

```text
zzm/
├─ pom.xml                         Maven 工程入口，Java 17
├─ src/main/
│  ├─ java/zzm/                    Java 后端
│  └─ resources/application.yaml   Spring 与 MySQL 配置
├─ frontend/
│  ├─ src/
│  │  ├─ App.vue、main.ts          应用入口、登录及页面切换
│  │  ├─ views/                  教师对话、任务编辑、学生学习、文件管理
│  │  ├─ components/             对话、弹窗、上传、材料树、讲义等复用组件
│  │  ├─ classroom-state.ts      当前用户、课程和页面状态
│  │  ├─ classroom-api.ts        接口类型及请求
│  │  ├─ useCourseMaterials.ts   材料加载与处理状态轮询
│  │  ├─ i18n.ts、locales/       中英界面文案
│  │  └─ classroom.css、design-tokens.css
│  ├─ public/                   正式静态资源
│  ├─ tests/brand-assets.mjs     图标生成工具，由 build:brand 调用
│  └─ Dockerfile、static-server.mjs、构建配置
├─ start.*、setup.*、compose.yaml、Dockerfile
├─ .env、config.json、config.defaults.json
├─ README.md
└─ 测试用材料不要删/              用户原始材料
```

在 IDEA 中打开项目根目录并导入 `pom.xml` 即可。后端只使用 Java；旧 Python 导出工具及未被使用的独立维护脚本已移出项目。

## 协作约定

- 前端交互与视觉设计遵循腾讯 [TDesign 设计指南](https://tdesign.tencent.com/design/values)，统一使用 [TDesign Vue Next](https://tdesign.tencent.com/vue-next/getting-started) 组件，保留项目品牌色；通用控件优先使用组件库，业务组件按实际调用关系复用。
- 只处理当前任务直接相关的源码与状态，保留已有工作区改动。前端按实际调用关系复用，避免重复校验、无调用方的兼容分支和无价值的抽象；不附加安全设计或依赖升级。
- Java 固定使用 17。MyBatis-Plus 保留 `IService`、`ServiceImpl`、`BaseMapper`，查询更新优先使用 Lambda 条件构造器，同一实体业务集中在对应 Service。遵循 Spring AI 官方接口，不增加零散的小包和小类。
- 材料状态归 `MaterialService`，格式解析归 `DocumentParser`，AI 提示与结果归 `AiService`，模型协议、重试及响应完整性归 `QwenClient`，后台调度入口为 `BackgroundJobs`。
- Java 类名用大驼峰，字段、方法及 JSON 用小驼峰，数据库字段用下划线；沿用 Lombok、Hutool JSON。
- 保持材料选择、题目导入来源、预览状态独立。保持已发布版本不可变，学习记录绑定明确版本；学生页面与教师学生预览均用公开内容投影，内部提示、参考答案和未审核反馈不展示给学生。
- Windows 操作使用 PowerShell 7，不启动代理。核对 AI 配置以实际进程、容器挂载和环境变量为准，不用空配置覆盖现有配置，不在输出中展示密钥。
- 编译、测试、启动以当次授权为准，不新增测试类或测试脚本，不运行无关的全量检查。临时启动的检查服务在检查后停止，用户要求保留的服务及原有服务除外。
- 后续开发统一使用 `master`，不再使用 `cys`。用户已要求本项目完成后直接提交并同步 GitHub，不创建 PR；新增提交留言仅使用实际提交时的北京时间，格式为 `YYYY-MM-DD HH:mm:ss`。不自行修改版本号。原课程材料、数据库和本机配置只按明确任务处理。
- 删除、清理统一移入 `C:\Users\user\Desktop\智能体回收站\垃圾桶`，不永久删除、不清空垃圾桶，不另外创建备份。
- 文档集中维护本 README，不保留历史验证流水，不再另建 docs 目录或交付报告。完成后同步 GitHub，交付实际改动、验证结果、未验证项及可核验的提交地址，交互功能由用户手动验收。
