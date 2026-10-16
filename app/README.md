# AIcademiya · 对话教学平台

项目结构与逐模块说明：[2026-10-14现状整理报告](../docs/project-review-20261014/README.md)。文档入口：[DOCUMENTATION.md](DOCUMENTATION.md)。

**当前内网网站：<http://192.168.32.55:18773/>（PVE CT255）。**

网站界面为英文，生产环境关闭演示登录。三角色、课程版本、材料/题目来源、worksheet 导入、账号回收站和跨刷新草稿已实现。原 CT254 已在用户随后明确确认后永久删除；容器配置及独占磁盘均已核验不存在。

## 当前对话教学更新

已上线 `AIcademiya_V2-stage16-workflow-r4`（API0.11.0/schema9），保留已有账号、课程和学习记录。最新部署及验收见 [DEPLOYMENT_STAGE16_RESULT.md](DEPLOYMENT_STAGE16_RESULT.md)。学生以一个对话框完成回答、追问、修正与自然推进；材料和历史答案位于辅助面板。教师在 Teaching setup 编辑目标、指令、反馈策略与流程；背景/高级选项/来源技术信息按需展开，私有试聊与保存草稿同屏。

新建session默认在充分作答后主动提供参考对照；旧版本保留原规则。内容修改仍需保存草稿并发布新edition。真实会话可导出HTML/TXT/JSON，时间来自实际记录；可选练习不代替显式提交和教师确认。

**Stage16完整资料处理已启用（沿用Stage15图文架构）**：**新上传 → 原生文字/Markdown表格与原图保留 → 来源校订 → 发布版本绑定 → 实际图文教学与引用**。支持PDF、PPTX、PPT、DOCX、DOC、XLS、XLSX、TXT、MD、PNG/APNG、JPG/JPEG、WebP，完整上传64MiB/1000页或帧；轻量预览仍为25MiB。`Read complete document`查看结果，`Review this source block`校订；校订不会自动发布。旧文件和失败任务不自动重跑，需显式重新处理/重试。原件、旧好版本及历史edition保留，机器转写不自动变成教师核准。

材料现分为 **Course Materials课程库 / Session Materials关联子集**。多文件上传自动入库并关联当前课次；通过下拉复用文件，不复制原件；从Session移出不删除课程库、其他课次或历史版本。标题/可见性/提取结果为共享文件属性，发布仍是显式操作。

Stage16新增文件夹选择、选中文件路径/大小、真实上传进度、逐文件type与已上传type编辑、直接移除入口；预览/完整处理/混合批次提示分别显示。Home支持Session编辑、草稿删除和恢复。AI连接每30秒轻量检查，生成测试单列。Questions & answers从已上传Materials选择Worksheet与可选私有Answer key，默认AI识别、老师审核后保存，不重复上传原件、不生成缺失答案、不自动发布。Excel使用全sheet/stored-cell原生账本与原始媒体预览，不冒充打印布局，公式原文与缓存值分开保留。

PDF默认在新标签页打开鉴权预览，Chrome/Edge均已实测。轻量预览保留本地CPU OCR和覆盖说明，已有文件可点 Re-extract text / OCR；完整PDF使用上述独立GPU后台流程。Enter发送、Shift+Enter换行；Quiz不重复题目卡；现用用户指定的 LOGO_V4 平滑矢量版；Stage8仅加强非书本轮廓，书本线条保持原样。早前网页研究与图标发布见 [STAGE5_RESULT.md](STAGE5_RESULT.md)。

教师工作台现在同屏提供已保存草稿试聊、Instructions & source review 和指令文件确认导入。打开不自动推理，保存变化后旧测试会过期，Reset my preview只重置本人的当前草稿测试。导入仅Apply到未保存指令，不自动保存或发布。学生记录新增Process overview，事实概览可定位原消息/修订，不以AI赞美代替教师确认。

Stage7采用统一的森林绿主操作、深正文、蓝色信息/焦点、琥珀提醒与红色错误；页面标题保留衬线，控件/阅读/数据使用非衬线。短帮助支持悬停、键盘和触摸；全局导航与品牌首页链接保护未保存编辑。V4图案保持，Stage8只加强非书本轮廓并调整品牌展示。

一级Settings包含所有用户的Account/Feedback，管理员专属AI Model/Web Search/Global User Accounts，以及教师的Course Students。正常产品不提供AI模拟模式选择（与用户意见Feedback模块无关）；Active AI Model显示模型和真实最近检查，不把配置存在当连接成功。Course materials/Learners/Publish & versions位于课程层，课次只保留四类教学任务。

课程横幅旁 **Course actions → Edit course / Move to trash**；Course Home右上 **Trash → Restore course**。编辑只改当前草稿的代码/名称/简介，发布后才更新学生端课程信息。回收站保留同一课程和全部关联内容，立即关闭学生访问；没有永久删除或课程自动清空。恢复保留邀请码和原课次开放规则，不重置已有账号/成员归档期限。

登录页已按最新选择采用浅底绿色图标/文字，正式登录与注册正常可用；无固定EDUC7703课程标识、匿名模型徽章或外部重复页头。侧栏保留绿色反白面板，改为Logo左、名称/副标题右的横排。V4全部资产和线条保持本轮改动前原样，1440/390/3771已实测。历史离线比较预览仍可查看，不代表当前线上配色。

当前生产部署与备份位置见 [DEPLOYMENT_STAGE16_RESULT.md](DEPLOYMENT_STAGE16_RESULT.md)；材料架构见 [STAGE15_MULTIMODAL.md](STAGE15_MULTIMODAL.md)。历轮Stage结果保留为历史记录。

线上推理路由已接通T10-B视觉能力，三张卡仍各保留64K配置，另外两张卡不受图像排队阻塞。已实测全新资料处理、原图教学、表格引用、基于来源出题、取消返卡及重启/恢复。原文与视觉Markdown通过稳定主视图避免重复计数，全部原内容保留。该发布不等于23份语料全部逐字/逐图核准；复杂图表和局部转写仍可回到原图核对。历史研究与失败证据见 [STAGE14_LIVE_STATE.md](STAGE14_LIVE_STATE.md)。

## 公网测试前安全准备

Stage10安全修复已部署，题图现按账号/课程/edition授权，认证/邀请码节流、Host/Origin及浏览器跨站校验、请求体与Office/图片/名单解析前限额、私有缓存/防嵌入响应头已启用。全部原23张表与历史资源保留，详见当前安全交付报告。

**Settings → Global User Accounts → New student registration**：管理员可关闭/开放学生自助注册，保存后独立回读。关闭不影响已有账号登录或授权教师手动建号；开放仍须课程邀请码。当前保留用户已有的关闭注册状态。

**本轮没有开放公网。** 当前地址仍是内网HTTP，不能直接映射18773作为安全上线。下一步须配置实际HTTPS域名、Secure cookie、精确allowed Origin与可信反代IP、后台网络隔离及入口连接/body/上传超时限制，再从最终公网域名验收。应用保持one-worker；进程内限流不是完整互联网DoS防护。

## 使用入口

- **Admin**：管理获分配的课程，以及全局模型/搜索、所有角色账号、课程人员分配与主负责人交接；不自动获得全部课程教学内容。
- **Teacher**：管理明确获分配的课程（可多人共同管理）和这些课程的Students；不能改全局角色、模型设置或管理其他课程学生，私有preview仍按本人隔离。
- **Student**：加入课程、作答、追问、查看自己的版本化历史与导出记录。
- 左下角头像或 **Settings → Account**，可上传/更换/移除头像、改显示名称；改密必须校验当前密码。头像支持静态PNG/JPEG/WebP，最大5MiB，居中256px裁剪预览后显式保存。
- **Settings → Feedback**：提交Bug/Idea/General并查看本人历史/回复；管理员同页进入 **Administrator inbox** 查看和回复、标记New/Reviewed。Reviewed不是已解决，暂不发送邮件或自动收集学习记录。
- 教师的 **Course Students** 支持单个创建/关联已有Student、CSV/XLSX预览导入、课程移除与恢复；空临时密码可用于已有Student且不重置账号。临时密码账号首次登录须改密。归档保留30天，到期按课程/全局授权范围清理，不删除共享课程资料。

## 多课程与全局账号

浏览器标题不再固定EDUC7703：登录/全局页面只显示AIcademiya，课程页面随实际课程代码变化。课程介绍保留原换行/空行，宽度自适应横幅；编辑对话框最大900px，手机内收。课程显示实时Sessions/Admins/Teachers/Students数量，1为单数，0或多人为复数，按本课程实际关系而非全站人数统计。

管理员 **Global User Accounts** 可搜索/筛选全部角色，单个创建、CSV/XLSX指定角色预览导入、修改他人角色、停用/恢复。账号导入两种格式均2MiB/1000行，新账号首次登录改密；已有同角色跳过，不批量改旧角色/密码。角色修改撤销目标会话但保留学习记录。

同页 **Course staff assignments** 可将多位Admin/Teacher分配至课程。先 **Make primary manager** 交接，再移除原主负责人的分配；改为Student前须先移除staff关联。不能移除最后有效课程管理人员，也不能自行降权/停用或丢失最后可用管理员。课程权限不会因拥有全局Admin/Teacher角色自动获得。

## 教学与内容

- 课次标签为 Teaching setup / Materials / Questions & answers / Student work。Course materials / Learners / Publish & versions位于课程导航；Course Home也提供课程材料入口。
- 保存课程草稿不会立即替换学生使用的发布版本；发布生成不可变版本。比较、恢复旧版本均保留原学习记录，恢复会创建新版本。
- 题目 Source 可多选文件/Link、添加 URL 或 DOI；留空表示使用全部合适材料。解除一个关系不会破坏别题或历史版本的来源。
- PDF使用独立鉴权预览，图片/文本保留基础预览，Link 可直接打开。网络提取失败会提示，不把链接元数据冒称完整原文。
- DOCX/PDF/TXT/MD/PPTX worksheet 导入后先复核题目、题组、参考与图片，再保存草稿并发布。独立材料额外支持PNG/JPEG/WebP及Office/PDF嵌图CPU OCR；覆盖统计和跳过/失败说明可查看，OCR不等于理解图表，扫描件和复杂排版仍需教师复核。
- Open/Closed/Scheduled 状态控制学生写入；配置时间范围时以时间为准。关闭/历史版本只读，保留授权的历史与导出。
- 未发送对话与未保存答案在本机浏览器跨刷新恢复，按账号、课次、版本、题目及用途隔离；不等于已提交答案，也不跨设备同步。
- 保留真实 EDUC7703 课程来源。参考的资格与展示方式由教师配置，旧发布版本保留原策略；不做正式自动评分，教师确认/退修流程保留。

## 模型与搜索

当前通过 CT255 的 `127.0.0.1:18280` socket proxy 接入 `aicademiya-router`，模型 `AIcademiya-64kx3-Qwen3.8-27B`。本应用 provider、精确模型判断和环境配置保留服务端HMAC缓存作用域及600秒超时。三副本与64K配置保留，KV按既有缓存策略运行；文档任务排空T10-B教学请求并取得独占租约，V100/T10-A继续教学，文档进程清理且GPU实际释放后再恢复第三个教学副本。不再采用文档模型与T10-B教学模型共驻留。

学生与教师预览的 **Web search** 默认关闭。打开才执行检索；真实来源独立保留为可点击链接。管理员在 Settings → Web Search 保存Tavily配置并显式测试，兼容服务器现有环境key；留空保留，明确清除会阻止旧环境key重现。key仅留服务端；错误显式报告，生产不执行模拟回复。配置/打开页面不自动probe。

## Windows 本地开发

### 中英文分支

`vue-java-cys` 用于英文交付，`vue-java-cys-chinese` 用于中文展示。两边共用 Vue 组件、业务逻辑和 `frontend/src/locales/en.json`、`zh-CN.json`。两个分支只在 `config.defaults.json` 中的 `frontend.locale` 默认值不同：英文为 `en`，中文为 `zh-CN`。

`config.defaults.json` 提供可提交的默认配置；个人设置和密钥仍集中在不进入 Git 的 `config.json` 中，后者优先。`config.json` 不填写 `frontend.locale` 时随分支切换，显式填写则固定为指定语言。切换分支后重启本机服务并刷新页面。无需为语言切换重复构建，两个分支使用同一份前端产物。登录页和页面顶栏也可临时切换语言；刷新或重新登录后恢复部署默认值。

界面语言只影响操作文字、日期和已知系统提示。课程原文、题目、答案、资料及 AI 教学语言仍按原内容和教学设置处理。第三方或尚未收录的错误原文会保留，便于排查。

后续功能修改应先在英文分支完成，更新两种语言资源；获得提交授权后，再将英文分支合并到中文分支，保留中文默认值。验收时运行 `git diff vue-java-cys vue-java-cys-chinese --name-only`，正常应只显示 `app/config.defaults.json`。无需为两种语言分别维护页面或业务代码。

当前 `vue-java-cys` 分支已将前端迁移到 Vue 3 + TypeScript，后端沿用 FastAPI。此分支的本机运行方式见 [本机运行说明](LOCAL_SETUP.html)，实际截图和待验收项见 [Vue 视觉检查记录](../docs/frontend-vue-review-20261016/report.html)。上面的 Stage 文档描述历史生产环境，不代表本轮已经重新验证。

双击 `start.cmd`，或在 app 目录执行 `pwsh.exe -NoProfile -File .\start.ps1`。默认地址 <http://127.0.0.1:18773>。所有部署设置集中到 `config.json`，相对路径按该文件位置解析，修改后重启。本轮使用隔离的 `data-local` 与 `local-demo` 合成课程。

本机分支默认接入硅基流动：`ai.provider=siliconflow`，`ai.base_url=https://api.siliconflow.cn/v1`，`ai.model=Qwen/Qwen3.8-27B`，`ai.mode=openai`。密钥填写在不进入 Git 的 `config.json` 的 `ai.api_key`，只由后端读取。超时、温度、思考开关和思考预算也在同一文件中；默认直连、120 秒读取超时、温度 0.3、关闭思考。缺少密钥时不会尝试调用。调用方式依据[硅基流动官方文档](https://api-docs.siliconflow.cn/docs/api/chat-completions-post)，模型名依据[官方模型目录](https://www.siliconflow.cn/models)；连通性检查与教学质量验收分别进行。

```powershell
pwsh.exe -NoProfile -File .\start.ps1 -Check
# 在 frontend 目录执行
npm test
npm run build
```

## 部署、数据与升级

- 当前程序：`/opt/aicademiya/current` → `releases/AIcademiya_V2-stage16-workflow-r4`。
- 生产数据：`/var/lib/aicademiya/aicademiya.sqlite3` 与 `uploads/`。
- 私有配置：`/etc/aicademiya/aicademiya.conf`；服务：`aicademiya.service`。
- 验收使用独立 `/var/lib/aicademiya-qa/`，所有临时 QA 服务已停止；未向生产库灌入验收账号或答案。
- 普通升级继续使用 CT255：校验新发布包、备份数据、验证 schema 兼容性、切换 release 并回读。数据与配置不随代码目录替换。保留仍被历史材料路径引用的旧 release。
- 数据恢复只能写入新目录；当前材料、历史快照及待提交导入资源都必须重定位并校验。代码、静态题图、配置与数据备份分开保管。

运行指南：[RUNTIME_V2.md](RUNTIME_V2.md)；备份恢复：[BACKUP-RESTORE-V2.md](BACKUP-RESTORE-V2.md)。
最新验收与部署结果：[DEPLOYMENT_STAGE16_RESULT.md](DEPLOYMENT_STAGE16_RESULT.md)。本轮本机复测见 [verification.md](../docs/project-review-20261014/verification.md)，其中记录Node26的Web Storage测试环境条件。V2初始交付见历史部署文档。

研究原件与私有课程材料不进入公开 Git/发布渠道。早期部署/验收文档保留为历史记录，不是当前启动说明。
