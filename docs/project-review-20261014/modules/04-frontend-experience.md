# 04｜前端界面与状态管理模块审阅

## 1. 模块作用与整体结构

前端把平台账号、课程管理、教学编辑和版本化学习放在同一应用壳内。角色决定一级 Settings 的能力，课程分配决定具体教学资源访问；草稿、服务端结果和不确定写入的恢复状态分别保存。

当前交付基线为 **Stage16 R4 / API 0.11.0 / schema 9**（`app/DEPLOYMENT_STAGE16_RESULT.md:L5-L24`）。页面使用英文，中文报告解释职责和证据。`app/frontend/package.json:L16-L31` 声明 React19、TypeScript、Vite、lucide-react、react-markdown、remark-gfm 和 Vitest/Playwright；版本号是声明范围。`main.tsx:L1-L12` 使用 ReactDOM.createRoot + StrictMode 挂载 App，`app/frontend/vite.config.ts:L5-L11` 为开发 API 代理和 dist 构建配置。

本次静态 import/export/dynamic-import 盘点得到 `frontend/src` **93 文件：72 个 TS/TSX、21 个 CSS，共 25,377 行**。从 `main.tsx` 的静态依赖可达全部 93 文件；这包括类型导入，说明不能依据名字筛出可直接删除的文件。实际正文/关键读段及测试范围独立记录在 `../evidence/frontend-learning-review-coverage.json`，核验范围集中列于第 9 节。

## 2. 用户入口、路由与权限边界

应用采用手写 hash route，不依赖 React Router。`routes.ts:L21-L57` 解析/序列化 page、sid、uid、version_id；settings 的 section 编入路径。旧 `profile/accounts` 路径继续映射到 Settings（`App.tsx:L203-L210`）。

| 页面/入口 | 组件链与角色 |
|---|---|
| Login/首次改密 | `App → Login/ChangePassword`；bootstrap/me 识别登录，must_change_password 先进入改密。`App.tsx:L53-L70,L168-L190`。 |
| Course Home | `Home`；staff 编辑课程、课次和回收站，学生加入课程/进课次。Home 卡片挂载 SessionActions/DeletedSessions。`App.tsx:L275-L292`、`Home.tsx:L321-L323,L426-L430`。 |
| 教学课次 | `TeacherSession`；Teaching setup / Materials / Questions & answers / Student work；draft 保存与出版分开。`App.tsx:L240-L254`、`TeacherSession.tsx:L140-L166,L410-L457`。 |
| 学习/记录 | `LearningWorkspace → GuidedLearningWorkspace`；workspace、staff preview 和只读 student record 共用布局，使用不同参数和 key。`App.tsx:L256-L273`。 |
| My Learning | `LearningHistory` 用 `/api/history` 获取独立 run 索引，每次打开传 saved edition。`LearningHistory.tsx:L15-L28,L56-L74`。 |
| 课程资源与出版 | `CourseLibrary/Versions/CourseTrash/CourseStudents`；与 session 的教学任务层级分开。`App.tsx:L211-L239,L352-L355`。 |
| Settings → Account/Feedback | 所有角色；Profile、Feedback。`SettingsWorkspace.tsx:L35-L72`。 |
| Settings → AI Model/Web Search/Global User Accounts | admin；保存全局配置、注册开关与账号管理。 |
| Settings → Course Students，或课程 Students | teacher/admin 的课程人员视图；只管理服务端返回的已分配课程。 |

`canAccessRoute` 的 role gate 负责页面可见性；课程授权由 API 再核验。teacher 可进入旧 accounts route，但 `SettingsWorkspace` 转为 CourseStudents，不挂载 GlobalAccounts（`routes.ts:L59-L63`、`SettingsWorkspace.tsx:L67-L72`）。App 的课程列表加载有 account/role/password scope 和 generation，避免旧账号迟到结果替换新账号课程（`App.tsx:L45-L99`）。

## 3. 六个易误判的“重复组件”仍在使用

| 文件 | 实际导入/调用链 | 结论 |
|---|---|---|
| `LearningWorkspace.tsx` | `App.tsx:L19,L258` → 文件 L2 re-export | 2 行门面，保留稳定 import 路径。 |
| `GuidedLearningWorkspace.tsx` | LearningWorkspace L2 → export default L67 | 当前完整学习、preview、record 实现。 |
| `AdminAccounts.tsx` | SettingsWorkspace L8/L71 → AccessSettings + GlobalAccounts（L20-L23） | admin 聚合包装，注册开关和账号面板都有作用。 |
| `GlobalAccounts.tsx` | AdminAccounts L3/L22 → AccountsPanel（L337-L419） | 全局角色/停用/恢复/导入与课程 staff assignments。 |
| `CourseStudents.tsx` | App L24/L218 + SettingsWorkspace L9/L72 → CourseStaff + Roster（L76-L86） | 课程 selector 和两条人员操作 lane 的容器。 |
| `Roster.tsx` | CourseStudents L4/L82 → ProvisionStudent + roster API | 课程学生关联、导入、移除/恢复与保留期。 |

这几组分别是 **稳定门面/实现**、**管理员容器/账号面板**、**课程容器/名单操作面板**。全局账号与课程 enrollment 的区别对应 `CONTEXT.md:L3-L13`，不是历史版本重叠。`stage2.ts` 有多处活跃 import，`stage2.css` 在 `main.tsx:L7` 全局加载；旧 Stage 名字只标记历史来源。

## 4. 页面数据流与组件职责

### 4.1 学习工作区

`GuidedLearningWorkspace` 持有 workspace、pinnedVersion、busy/pending、composer、辅助面板、参考、review note 与滚动状态。初次 GET pin 服务端 edition；所有后续 turn/reference/answer/submit/review/export 使用该 version（L86-L155、L394-L468）。任一 mutation 完成后独立 GET workspace；pending 时 2.5 秒轮询读取（L227-L259、L328-L344）。

`TutorMessage` 以保存的 `metadata.presented_question` 为题卡，旧消息才回退到 required question 查找；source_labels、options、原图和 public presentation 均保留（`TutorMessage.tsx:L19-L119,L179-L191,L266-L280`）。`guided-study.tutorNarrative` 检查 narrative/suffix 与原 content 一致，只抑制 byte-exact 已渲染末尾题目，不改数据库/导出（L43-L94）。

`SavedResponses` 是辅助编辑面板，保存个人 scoped answer draft、历史 revisions 和旧 answer/ask 草稿入口；主对话与单独 Save response 保留不同用途（L44-L74,L146-L170,L180-L208）。`TeacherProcessOverview` 通过工作区的消息/修订定位入口使用，定位必须是实际 message ID（`GuidedLearningWorkspace.tsx:L490-L505`）。

Enter/Shift+Enter、IME/keyCode229、重复或修饰键分支由 `composerEnterAction` 统一处理；single_choice 插入裸字母，其它 option bank 保留选项文字（`guided-study.ts:L23-L40,L131-L140`）。模型 prose 经 Markdown 展示，learner raw content 作为 React text，模型提供的图片不会直接请求外部服务（`TutorMessage.tsx:L239-L246`、`TeachingText.tsx:L17-L38`）。

### 4.2 教师同屏工作台

`TeacherSession` 分开 saved session 与 unsaved draft；保存验证后更新两者、清 dirty，提示 Publication is separate（L49-L71,L140-L166）。Materials 回读只替换 materials，保留其它未保存编辑（L417-L425）；worksheet 导入前要求 save/discard 其它 dirty 内容（L432-L444）。

- `TeachingFramework/teaching-profile.ts`：教学目标、反馈策略、phase、reference eligibility/delivery 和编译 preview。缺失历史 profile 保留 on_request；freshness key 包括 profile、instructions、goals、language、reference_policy（`teaching-profile.ts:L27-L52,L132-L170`）。
- `TeachingSourceReview`：保存的 question/material binding + 可选未保存 instruction overlay；数据变化隐藏旧结果、忽略迟到响应，显示实际 snippet codepoint 用量（L10-L16,L44-L86,L149-L161）。
- `InstructionImport`：提取 → 本地审核 → append/replace Apply；Apply 更新未保存 Additional instructions。request/edit generation 保留提取期间较新审核文字（L47-L79,L97-L100,L123-L142）。
- `TeacherPreviewPane`：同屏 private、saved draft。GET workspace + previewInfo 验证相同 generation/revision；显式 start 才 reset/bind 或调用 tutorStart。按 viewer/preview-run 保存草稿和 retry，busy/stale 不接受新 turn（L77-L94,L128-L161,L218-L303）。同屏此路径固定 `web_search:false`（L285-L292），Web search 控件在完整 workspace。

保存按钮受 previewBusy 保护；教师仍可作未保存编辑，试聊继续使用 saved。preview_id 与 saved_revision 的服务端界限详见 03 报告。

### 4.3 上传、复用与资料读者

`MaterialManager` 负责选择文件/文件夹、逐文件类型/可见性、上传队列、session attach/detach、共享属性编辑。文件夹用 webkitdirectory，显示相对路径；XHR 字节进度区分“100% sent，等待服务端确认”（L245-L262,L334-L366）。`material-upload.ts:L19-L81` 选择时冻结 processing/maxBytes，串行执行，仅 queued/failed 会重传，answer_key 强制 teacher。

收到成功材料 ID 先保存到 queue，再独立读取 session 和 course library，验证 ID/元数据/关联（`MaterialManager.tsx:L117-L143,L156-L187`）。preview/full/mixed 成功提示只基于 accepted 文件（`material-upload.ts:L83-L89`）。Session Remove 回读关联缺失，课程原件与历史 edition 保留（`MaterialManager.tsx:L548-L552`）。

`WorksheetImport` 从 Course Materials 选择原 Material ID 和可选私有 key，AI 默认开；读回审核 draft，提交后 GET session 验证 prompt/参考，再清审核界面，保留“Save content draft”的语义（L16-L29,L41-L95,L108-L138）。

`Materials` 显示共享材料的状态、原件/鉴权 PDF、摘录/覆盖说明与 DocumentReader（L47-L49,L93-L167,L169-L219,L307-L315）。`DocumentReader`：

1. me + summary + capability 获取账号、当前 revision、可用能力；页请求带 exact revision/edition，generation/AbortController 避免迟到页数据（L119-L198）。
2. 图像资产仅接受对应 material/revision/edition 的 API 路径（`document-state.ts:L9-L29`）。
3. staff 当前 draft 才能 review/reprocess/share，先保存 request_id 与 expected_revision；未知 ack 恢复只用 receipt GET，不重复 POST（L63,L345-L383）。
4. receipt + 独立 summary/page 逐字段验证新 revision、source hash、block text/quality/audit 后清 pending（L258-L344；`document-state.ts:L49-L80`）。
5. 本 tab sessionStorage 保存 account/material/version 的 correction/pending，draft 自带 revision/page；关闭保留，冲突要求比较新 revision 后明确重确认。真实 queued/running job 才轮询，无编造 OCR 百分比（L87-L110,L136-L151,L200-L222；`document-state.ts:L31-L42`）。

### 4.4 账号、名单与 Settings

`accountApi` 全局 `/admin/users`、import-state 和 `/courses/{id}/staff` 显式区分；payload 不带客户端 actor 权限（`account-management-api.ts:L21-L62`）。`useAccountLane` 用同步 lock + mounted/generation 防双击/迟到 response；未知 mutation 进入 recovery（`account-management-state.ts:L105-L149`）。

Global import 成功后按 exact returned user IDs 分批独立 GET，每个 ID/role/name/initial-password-state 与 preview 对照；lost ack 用冻结 import-status GET 恢复（`GlobalAccountForms.tsx:L317-L383`）。账号编辑与 staff assignment 在独立 component/lane 中串行。

Roster 的 active/trash tab、selection、读请求与 mutation 共享同步锁；父 CourseStudents 在 staff/roster pending 时禁 course 切换，按 account/course remount（`Roster.tsx:L57-L100,L108-L164`、`CourseStudents.tsx:L49-L55,L72-L86`）。移除/恢复同时 GET 源和目标名单。课程 import 当前无 outcome GET，只有 current roster 和已收到的 ackResult；原 ack 丢失时 UI 明示“原提交未确认”，保留审核，不自动重提（`Roster.tsx:L219-L307`）。

Profile 以账号 key 重挂载；头像预览/保存/独立 me + image verification 与姓名/密码 draft 分开，保存头像保留其它编辑（L13,L81-L108,L170-L203）。Feedback 对个人 draft/request_id 用 account-scoped localStorage，提交通过 request receipt + target GET；admin 回复带 expected_revision，冲突保留回复文字（`Feedback.tsx:L97-L100,L195-L200,L339-L378,L421-L540`）。

Settings 共用 `useSavedSettings` 的 read/write/readback 与 edit revision；只有匹配独立 GET 才清编辑，晚到回读保留更新的 draft（`stage7-settings.ts:L140-L263`）。API keys 初始空白、replacement/clear 显式，保存在表单内存及服务端；浏览器持久草稿不包含 key（L25-L86）。轻量连接为共享 30 秒 visible 轮询，expires 明确失效，切账号/改配置/登出清理（`live-connection.tsx:L6-L29`、`App.tsx:L295`）。手动 Generation check 单独发送短模型请求（`ModelSettings.tsx:L170-L201`）。

## 5. 状态及跨刷新范围

| 状态类别 | 持久性/作用域 | 清理条件 |
|---|---|---|
| 登录/课程索引 | 服务端 cookie；App 内存及 scope-generation | 登出 POST 后 me=401 才清账号（`App.tsx:L130-L147`）。 |
| Composer / saved answer | localStorage；account/session/version/question/intent/preview-run | exact ack + 未改动 payload；保存 response 完成后的对应 scope。`drafts.ts:L1-L43`、`guided-study.ts:L214-L232`。 |
| Tutor pending | localStorage；account/session/version/preview-run | exact completed request ID；与正文草稿独立。 |
| 教学编辑 draft、worksheet 审核 | React 内存；account/session keyed | 保存/明确 discard；离开靠 navigation guard，刷新后不承诺恢复。 |
| Document correction/pending | sessionStorage；account/material/version，内部 revision/page | receipt 与 exact source readback；同 tab 刷新可恢复。 |
| 全局账号/名单/password/config编辑 | React 内存与 recovery/dirty 标志 | matching GET/显式放弃；密码和 keys 不写本机持久 draft。 |
| Feedback提交草稿 | account-scoped localStorage | exact request/payload readback。admin reply draft 为内存。 |
| 读界面、tab、缩放、scroll | 页面内存 | 挂载/导航；无需复制成学习事实。 |

`navigation-guard.tsx:L3-L23` 集中登记 dirtyForms、beforeunload；App 内部导航/hashchange/品牌主页/退出均调用 confirmNavigation（`App.tsx:L102-L143,L321,L404`）。提示统一说“离开会丢弃”，但 composer/document/Feedback 某些 draft 会保留。建议按持久状态分类优化文案，不撤掉 guard。

## 6. 页面依赖、布局与审阅时历史差异

父级已统一README/AGENTS入口，本节保留审阅时的Stage15导航残留来源。

界面层负责展示与局部状态，服务端负责最终课程授权、不可变 edition 和 mutation identity。`api.ts:L51-L75` 为 cookie-bearing request/ApiError，文档与账号 transport 各自扩展。`TeachingText` 控制 prose Markdown，`SourceCitations.tsx:L20-L79` 校验材料/源注释链接的 revision/edition，Web hits 保持独立“Retrieved sources”（L92-L114）。

CSS 由 design tokens、基础 styles 与专题样式构成；已选读 focus/reduced-motion/断点：`styles.css:L49-L56,L2511-L3294` 的相关匹配行、`guided-workspace.css:L965-L1266` 的断点、`teacher-workbench.css:L411-L425`、`document-reader.css:L171-L175`。布局断点按页层级分工。

Stage16 已把 Session edit/delete/restore、文件夹/类型/进度、Materials 复用 Worksheet、轻量连接轮询落到当前组件；Stage2-era 文件继续贡献 helper/style/兼容入口。README 上部最新工作流与 L31/L98/L106 的 Stage15 导航/旧 release 同时存在，建议统一当前入口后保留明确历史索引。

## 7. 已发现问题与建议优先级

### P2｜默认测试缺storage fixture；明确环境后400通过

父任务本轮 `npm test` 的日志 `../evidence/frontend-tests.log:L65-L90` 记录两项失败：`reference button stays visibly gated until submission`、`student markup never includes the server-only instructor answer`，共同为 `ReferenceError: localStorage is not defined`。

静态调用链已确认：

- `stage7-learning.test.tsx:L38-L55` 用 `renderToStaticMarkup` 渲染 `SavedResponses`，默认 `teacherRecord=false/locked=false`；该文件 L1-L58 未设置 localStorage mock。
- `SavedResponses.tsx:L64-L74` 在 render 中枚举旧 answer/ask drafts 并调用 readDraft。teacherRecord 测试 locked=true，绕过此分支，因此同组件的教师测试能过。
- `drafts.ts:L12-L19` 的 `storage=localStorage` **在进入函数体的 try 前求值**。Node 没有这个全局标识符，抛错先于 getItem 的异常捕获，两条目标 assertion 尚未执行。
- 生产入口 `main.tsx:L8-L12` 是浏览器 createRoot，正常浏览器有 localStorage；后端返回 dist/index.html（`app/backend/aicademiya/main.py:L578-L585`），没有本条测试的 React SSR 运行路径。

结论：**已确认测试 fixture/组件 SSR-storage 分支问题；现有日志没有证明参考 gate 失效、私有答案泄露或普通浏览器页面崩溃。** 默认npm test仍有2项环境失败；父级启用Node真实Web Storage并指定独立存储文件后400项通过，构建通过。后续可由维护者选择：测试注入 storage mock，或在 helper 内惰性取得默认 storage 以正式支持无 storage 渲染；本次按授权不改源码。部署 Stage16 的历史 400 passed 与本轮 398/2 是不同执行记录。

### 其它问题清单

| 优先级 | 证据类型 | 事实/影响与建议 |
|---|---|---|
| P2 | 静态确认的 UI 条件遗漏 | Materials 的 complete/status 入口条件 L170 没列新增 `ppt/xls/xlsx`，仅 document 已存在或 pdf preview 时可绕过。对无 document 且 preview_kind 非 pdf 的新格式，处理状态入口不显示。补当前 format 能力驱动的准入；父级真实React静态渲染合成processing材料已复现这三个格式缺入口；证据 `../evidence/targeted-ui-observations.json`。 |
| P2 | 静态确认的字符计数差异 | `teaching-profile.ts:L64,L179`、`InstructionImport.tsx:L79,L192` 用 JS .length（UTF-16），后端 `models.py:L103-L109,L142,L194` 是字符长度字段，source review 已用 Array.from。emoji/扩展字符使前端更早拒绝/用量偏大。父级复现600个emoji被计1200单位拒绝，后端接受600 codepoints；统一codepoint计数，保留超限文本。 |
| P2 | 已有恢复边界 | 已获 ack 的上传 ID 安全保留；XHR 连接丢失统一进 failed，可再次 Retry（`api.ts:L103-L104`、`material-upload.ts:L76-L79`、`MaterialManager.tsx:L389-L406`）。此 UI 只有“先检查课程库”的文字，没有 exact 原件 receipt 自动恢复。建议区分 rejected/unknown，避免把未知接受当确定失败；后端上传幂等另由材料模块核查。 |
| P2 | 接口能力差异 | Global account import 有 frozen receipt GET；Roster import 无 outcome GET（`Roster.tsx:L299-L307`）。当前 UI 正确保留 unknown，应在 API 文档列明，并按实际需求补收据，不复制全局恢复实现后宣称已确认。 |
| P2 | 静态确认的保存验证范围 | `saveTeachingDraft` 写 title/groups/questions/reference_answers，但独立 GET matcher 只比 teachingPreviewKey（`teaching-profile.ts:L182-L203`），缺标题/题目/答案的逐字段 equality。父级实际helper复现：改变title/questions/reference_answers后key仍相同。建议核对完整payload或receipt revision；这证明比较范围，不等于生产实际漏存。 |
| P3 | 维护建议 | GuidedLearningWorkspace 1,365 行、Feedback 999、DocumentReader 924、Roster 659；未来按 turn lane/document receipt/表单小单元拆分，现阶段保留行为回归。 |
| P3 | 文案事实 | 通用 navigation guard 把全部 unsaved 状态说成丢弃，与持久草稿有差异；按用途说明，不暗示全站跨刷新持久。 |

## 8. 不可清理与冗余整理建议

**保留**：六个活跃组件、stage2 helper/style、draft/pending/preview scope helpers、全局账号与课程名单双轨、全部 edition/history/source-reader 入口、历史 raw message presentation fallback、旧 answer/ask draft 恢复。静态图没有发现无入口源文件候选。

**整理方向**：

1. 统一 README 当前导航与历史 Stage 索引；文件名暂保留以免打断 import 和测试。
2. 对大组件提取共享状态原语前先列明差异：tutor done-id、document exact receipt、global import frozen receipt、roster current-state inspection 各自不同，不能合成“任何 GET 成功就清草稿”。
3. 基础 styles 与专题 CSS 存在多个相邻/重叠 media blocks。合并前检查实际 cascade 和桌面/手机截图；当前依赖可达，不能把重复 selector 当无效 CSS 删除。
4. 测试/harness/Stage 命名归档按当前 npm/浏览器脚本/发布清单调用关系核验。测试日志仍执行到 `artifacts/stage6-teacher/teacher-workbench.test.ts`（`../evidence/frontend-tests.log:L60`），所以 artifacts 下也有测试依赖；整体产物清理由父任务评估。

## 9. 核验范围与已读测试

本次执行了静态文件读取、精确读段/引用核对和 import 图统计；只写两份模块报告及一份覆盖 JSON。未运行 npm test/build、后端测试、浏览器服务、真实模型、网络或 SSH。父任务测试日志单独作为**父执行证据**，本次只解释失败链。Backend document/parser、provider/search 底层、真实部署和其它 UI 组件的全正文审计由父及其它模块承担。

已读测试包括：

- `stage3-student.test.tsx:L93-L259`：自然输入、request identity、draft scope/恢复/精确 ack；其它 presentation 测试选读标题。
- `stage7-learning.test.tsx:L1-L58,L125-L210`：两项 SSR 失败具体 branch、教师只读对照与材料/过程结构。
- `stage16-materials.test.tsx:L1-L49`、`stage16-worksheet.test.tsx:L1-L34`、`stage16-connection.test.tsx:L1-L18`：accepted-mode 提示、XHR fixture、材料复用 DTO、连接 TTL 的具体 assertions。
- `stage12-document-client.test.ts:L1-L142`：edition/revision transport、GET-only receipt、source review readback；document-ui 另选读测试入口。
- `stage11-personnel.test.tsx:L175-L311`：exact account GET/import transport 与已读边界；测试 role/policy/SSR 项另选读标题。
- `stage7-teacher`、`stage7-settings`、`stage9-account-feedback`、`study`：读指定测试声明/关键断言，范围详见 JSON。

父级匿名线上桌面/手机浏览器、独立构建与合成组件复现均完成，详见上层verification.md。logged-in复杂交互、IME和多标签延迟保留对应范围。静态图可达与正文审计范围分别记录。
