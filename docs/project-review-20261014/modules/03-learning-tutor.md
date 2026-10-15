# 03｜学习流程与教学对话模块审阅

## 1. 结论、范围与证据等级

以 **Stage16 R4、API 0.11.0 / schema 9** 为当前交付基线，来源为 `app/DEPLOYMENT_STAGE16_RESULT.md:L5-L24`。本次负责源代码与测试源码的静态审阅；父任务统一执行测试/build。执行范围集中列于第 8 节。

实际正文审阅覆盖 `guided_*.py` 六个文件、`learning_routes.py`、`evidence.py`、`reading_context.py`、`visual_context.py`，十个核心文件共 **1,957 行**；另外选读权限、workspace 投影、教师 preview 和前端学习状态链。精确读段/结构扫描/测试读段见 `../evidence/frontend-learning-review-coverage.json`。`ai.py`/web-search 底层、document 后端及解析工作器不在本报告审计范围。

主要判断：

- **应用拥有学习状态转移，模型给出受校验的形成性建议**。
- 回答、追问、原始消息、修订、参考公开、可选练习、显式提交、教师确认是不同数据面，不能在整理时合并。
- 两套 learning API 仍同时注册。旧 `/chat` 不是当前学生主界面，但没有成为可删除的后端死代码。
- 教材正文与原页图像具有分别计数的读取边界；完成读取不等于语义准确或全书理解。

## 2. 作用与用户入口

| 使用者/入口 | 实际能力与界限 |
|---|---|
| Student → Course Home → session | 自然语言单一 composer：回答、问提示、修正、选阅读支线；可选 quiz 明确同意后生成。 |
| My Learning → 历史 edition | 从用户已有 run 索引查找历史，而非依赖当前课程课次；旧 edition 只读，保留记录与导出。 |
| Teacher/Admin → Teaching setup → Tutor preview | 同屏私有试聊针对本人的已保存草稿，打开面板本身只读；显式 Start/Reset。 |
| Full preview workspace | 复用学习工作区，携带教师 preview 身份；该完整工作区的 not_started 会自动 begin，应与“打开同屏工作台不推理”区分。 |
| Teacher → Student work → record | 查看指定学生、指定 edition 的原消息/修订/过程事实，显式 confirmed 或 needs_revision。 |

调用链是 `App → LearningWorkspace → GuidedLearningWorkspace`。`LearningWorkspace.tsx:L2` 是有意保留的导出门面，不是另一套学习实现；`App.tsx:L240-L273` 同时将 workspace 和 record 路由交给它。历史入口见 `App.tsx:L197-L201`、`LearningHistory.tsx:L15-L28`。同屏试聊见 `TeacherSession.tsx:L573-L580`；自动 begin 仅见完整工作区 `GuidedLearningWorkspace.tsx:L305-L326`。

## 3. 文件职责与活跃依赖

下列文件均位于 `app/backend/aicademiya/`：

| 文件 | 职责/关键代码 |
|---|---|
| `guided_routes.py` | 认证 route、请求预留、模型外部执行、原子提交、参考自动对照、HTML/TXT 原始转录。L25-L110、L112-L197、L207-L235。 |
| `guided_engine.py` | 纯内存状态机；检验 intent/target/outcome，控制 worksheet/quiz/reading/wrap_up/complete；返回 answer event，不直接写 DB。L13-L68、L81-L220。 |
| `guided_director.py` | JSON 协议、稳定教学系统段与动态 learner envelope；公共/私有上下文分流；检索开关与来源验证入口。L25-L112、L166-L284。 |
| `guided_reading.py` | 规划有限文档读取、绑定真实图片、验证引用；只对可修复的引用错误允许一次真实 provider 修订。L37-L77、L79-L170。 |
| `guided_state.py` | run key、持久化状态、公有投影、当前题选择和 metadata presentation；不向公有状态输出 quiz keys。L9-L49、L60-L136。 |
| `guided_migration.py` | 添加 metadata、tutor_runs/tutor_requests 的迁移；复合键及 FK 约束。L5-L28。 |
| `learning_routes.py` | workspace/history、选支线、单独保存答案、兼容 chat、参考资格、提交、教师观察与审核/JSON 导出。L21-L107、L109-L202、L204-L316。 |
| `evidence.py` | 轻量 excerpt 的可用性/隐私过滤及稳定排序，保留真实材料身份供来源复核；不是完整文档读取器。L9-L46。 |
| `reading_context.py` | 已授权 manifest 的正文主视图、查找/顺序游标、质量/容量门槛、D 引文逐读段核对。L30-L105、L197-L324、L328-L382。 |
| `visual_context.py` | 选最多两张原页图、单独限制 4MiB 原始图片字节、绑定 revision 和可见性、真实 image_url 与 V 引用。L13-L126。 |

`main.py:L396-L405` 注册 learning/guided/workbench；`db.py:L123-L126` 仍调用 guided 和 preview 迁移。因此 **Stage3 文件名/注释并不意味着过时可删**。依赖 `services`、`version_context`、`authoring.selected_tutor_materials`、`teacher_preview`、`teaching`，底层 provider/search/document 能力由其他模块供应，不能据此声称底层已全审计。

## 4. 具体数据流

### 4.1 一次 guided turn

1. 浏览器保存精确 `request_id/message/action/question_id/web_search/preview_id`，通过 version query 调用 `/tutor/turn`；run 成功或失败之后都再 GET workspace。见 `GuidedLearningWorkspace.tsx:L227-L259,L387-L432`。
2. 后端 `BEGIN IMMEDIATE` 后授权，生成内容指纹，检查同 ID 的 done/pending/failed/superseded；done 直接返回，内容不同为 409。首次 turn **先写真实 user 消息**，尚不接受学习答案或推进 phase。见 `guided_routes.py:L29-L102`。
3. 获得版本化教学 detail、状态、当题公共/私有材料与当前参考。模型在 SQLite 事务外执行；引擎 deep-copy 预留状态。见 `guided_routes.py:L103-L119`、`guided_engine.py:L13-L23`。
4. Director 组装稳定系统段、动态 attempt/history/read evidence；需要文档时先规划读取，再验证结构、target、intent/outcome、来源。真实 search 仅开关为真且 task=turn 时调用，不把私有教学参考送入该 search_session。见 `guided_director.py:L176-L240`。
5. 原子提交前再次检查课程/活跃 actor、pending request 所有权与 preview revision；保存 answer event、原消息 metadata、assistant、读取游标和 state，再标 done。见 `guided_routes.py:L120-L180`。
6. provider/协议失败保留 raw user 消息、标 failed、报 502；失败重试可能再次使用 provider，**不是 provider 侧幂等**。done 重试才不再推理；新显式 mutation 可把旧失败计划变为 superseded，防止覆盖较新的工作。见 `guided_routes.py:L47-L56,L189-L197`、`guided_state.py:L52-L57`。

### 4.2 学习语义与持久化

- run 主键为 `(session_id,user_id,version_id)`；教师草稿 DB version 为空字符串，浏览器 DTO 是 null。messages/revisions/attempts 与 tutor state 各自存在，不可仅存最后回答。`guided_state.py:L9-L32`、`services.py:L121-L162`。
- worksheet 只有 answer/mixed 且有效 target/outcome 才产生 answer event；明确 hint/review/pure_help 强制 ask，不能覆盖答案。`guided_engine.py:L111-L164`。
- sufficient 的含义是可继续讨论，status=discussed，并非正式掌握；单独编辑保存答案会把对应 guided 状态重开为 in_progress/unknown。`guided_engine.py:L140-L147`、`services.py:L121-L135`。
- quiz 五题、明确 opt-in，服务端产生并持久化 ID/keys；每题一次形成性作答。字母/数字选项可确定性计分，其余输入使用模型 outcome。reading 的 needs_retry 留在本题，sufficient 才继续；可选答案不混入 required attempts。`guided_engine.py:L165-L209`。
- complete 仍可课程追问/修改实际尝试过的题，但没有新 required work；submitted/confirmed 才锁定编辑，needs_revision 可继续。`guided_engine.py:L105-L110,L210-L212`、`services.py:L102-L104`。
- 提交要求选好 reading branch 且 active path 全题有非空答案，不要求每题 sufficient；教师审核另行显式执行。`learning_routes.py:L244-L255,L300-L310`。这不是自动评分系统，不能用 quiz correct 或 discussed 替代提交/确认。

### 4.3 参考资格与展示分离

`after_attempt/after_feedback/after_submit` 是资格，`on_request/after_sufficient_answer` 是展示策略。缺少 profile 的历史内容保持 on_request（`teaching.py:L5-L10`）；新默认自动对照不能回填旧快照。显式参考要求当前题有实际作答、满足反馈/提交条件（`learning_routes.py:L204-L229`）。自动对照由服务端在 sufficient 提交后进行，仍检查当前 edition、开放、成员归档、提交状态与资格，然后插到下一题之前（`guided_routes.py:L150-L168`）。

模型只看到服务端当题私有参考用于指导，不获得“可公开”的自由裁量。未公开参考的重复文本检测与一次反馈改写见 `guided_director.py:L38-L67,L265-L269`；这是有限文本防护，不能保证所有隐喻/短答案/释义都不泄露。

### 4.4 来源正文、图像与引用

完整文档路径先收到授权材料绑定，而不是任意路径/URL。`reading_context.py:L1-L4` 明确自身不授予访问；责任在上游课程/edition/材料选择器。

- 轻量 excerpt 只纳入 ready/needs_review、student 可见且非 answer_key 的材料；公共预算 32,000 codepoints、单条最多 4,000。完整文档正文只接受 extracted/approved，needs_review/excluded 不自动升级。`evidence.py:L4-L37`、`reading_context.py:L15-L16,L298-L304`。
- planning 最多四个材料请求；guided 正文窗口 18,000 字符/UTF-8 字节、单块最多 6,000。lookup 支持指定页/块/关键词；sequential 禁止跳页选择器。`guided_reading.py:L44-L69`、`reading_context.py:L74-L100,L218-L223,L272-L294`。
- whole-page Markdown 是有明确 provenance 的只读主投影，不按近似文本删重。优先保留 approved 原文；alternative 原块仍可明确读取，计数单列。游标绑定 revision、supplement scope、view policy/sequence，成功 assistant commit 后才持久化。`reading_context.py:L18-L69,L197-L261`。
- 文本不可靠不妨碍原页图像；图像进度独立于文本进度。图片从授权材料的 exact revision/root 取原字节，验证格式/像素/单帧，真正附到模型消息后才允许 V 引用；公有 metadata 不保存 base64/path。`visual_context.py:L17-L64,L67-L125`。
- D 引文仅对本轮实际供给 ref 的具体 text 验证；仅允许同一 Markdown HTML cell 的 `<br>` 表示为空白，并记录 raw span，禁止跨 cell/更换数字/大小写/其它 markup 松绑。`reading_context.py:L328-L382`。
- 一次引用修复不能新增 intent/progress；生成 quiz/readings 时使用 citation-only schema，不发送 private items/keys，不改公开 introduction。`guided_reading.py:L107-L170`。

## 5. 跨刷新、版本和权限

| 边界 | 当前实现 |
|---|---|
| 浏览器刷新 | composer/draft 是 localStorage，不是已提交记录；pending identity 单独保存，只有 exact completed request ID 才清除原请求和未改动的提交草稿。`drafts.ts:L1-L43`、`guided-study.ts:L108-L122,L164-L232`。 |
| 题目/用途/preview | 草稿细分 account/session/version/question/intent/preview-run；pending 按 account/session/version/preview-run 保存，故跨题推进仍可确认旧 turn，而不会清掉新题草稿。 |
| 发布与历史 | 所有学习读写/reference/review/export 应使用已加载 edition；旧版与未开放/归档禁止新写，unversioned stale write 拒绝。`version_context.py:L71-L109`。 |
| 推理中发布/关课 | 已接受推理提交回原 requestkey；仍重查课程/权限/保留状态，而非把结果挪进新 edition。`guided_routes.py:L120-L129,L182-L187`。 |
| 教师 preview | `(session,user)` 的 preview_id 与 saved_revision；有意义的保存使旧试聊 stale。reset 拒绝 pending，只删除该 staff 的当前 unversioned run，不碰学生、别课次或发布 run。`teacher_preview.py:L25-L38,L65-L111`。 |
| admin 与课程 staff | 全局 admin 不是全部课程教学权限；course_access 检查 live actor + explicit assignment 或 enrollment。学生历史只限已有 run，移除 staff 的草稿不可变成 student history。`version_context.py:L20-L31,L99-L107`、`learning_routes.py:L44-L55`。 |
| 导出 | JSON 是 workspace 投影；HTML/TXT 保留原消息、可选回答及真实 timestamps，elapsed 是跨度不是学习时长。HTML escape/no-store/CSP sandbox。`learning_routes.py:L258-L267`、`guided_routes.py:L214-L235`。 |

## 6. 当前实现与审阅时旧文档

父级已更新README/AGENTS入口；以下保留审阅时版本差异来源。

Stage2 `AGENTS/CONTRACT/BUILD_CHECKPOINT` 不作为当前需求或修改授权。当前 teaching 流程已是 guided，而不仅是 answer-vs-ask 的旧表单；但 `/answers`、`/reading`、`/references`、`/submit` 仍被辅助面板调用，legacy `/chat` 也仍在路由及协议回归中。

Stage15 的历史“未部署/等待 router”checkpoint 不能覆盖其顶部已交付结论，Stage16 同理。`README.md:L9-L21` 已介绍最新工作流，但 L31/L98/L106 仍指 Stage15 部署/旧 release；应由父任务统一文档修订，不在本次改现有文件。

## 7. 问题与建议优先级（不代表本次修改）

| 优先级 | 类型 | 事实与处理建议 |
|---|---|---|
| P1 | 已有产品限制，不是新复现漏洞 | 未公开答案检测依赖较长 literal substring 与提示约束，不能承诺语义不泄露。Stage15 文档 L79-L82 保留过早说答案/图像误认的真实失败；当前 citation-only 修复已解决其中生成修复泄露，不能重报为未修复。维持真实质量样例与公开边界，不为通过而制造回复。 |
| P2 | 静态观察/待验证 | 浏览器只获得 `last_completed_request_id`，无此模块的逐请求完成收据 GET。跨标签页后一请求完成，可能让遗失旧 ack 的本地 pending 无法仅凭最后 ID 确认；不等于 DB 重复写。见 `guided_state.py:L42-L49`、`guided-study.ts:L214-L232`。建议父任务有需求时补 exact-receipt/多标签 lost-ack 测试。 |
| P2 | 接口语义差异 | guided 在验证成功才保存 answer event；legacy chat 的 answer intent 在推理前就保存 attempt，失败仍保留答案。`learning_routes.py:L134-L160` vs `guided_routes.py:L83-L90,L140-L142`。整理 API 文档须明确，不能用统一“失败没有答案”描述二者。 |
| P2 | 文档事实 | README 当前/历史部署链接混杂，见上一节。不要按旧 checkpoint 清理最新代码/迁移。 |
| P3 | 维护建议 | director/read planner 的规则和 schemas 集中，压缩写法/长 prompt 可读性低；未来只在功能修改时抽公共小单元并留协议回归，不应为报告做架构重写。 |

本次发现集中在接口语义、完成回执与文档一致性。

## 8. 已读测试证据与不可清理项

本次读代码和指定测试源码，未运行测试/build、浏览器服务、真实模型、网络或 SSH。底层 provider/search、document 后端与工作器由其他模块报告承担。进程中断 pending 恢复、真实 IME、复杂图表质量、跨设备/多标签一致性留给后续执行验证。父任务默认前端测试 **398通过/2失败**；明确Node Web Storage环境后 **400通过**，后端1364通过/1跳过。两项默认失败为Node静态渲染缺少localStorage，见04报告第7节与上层verification.md。

已读测试覆盖以下协议：

- `test_stage3_guided.py:L122-L199,L203-L236,L273-L299`：混合回答/追问、自动参考、可选练习隔离、失败保留、done 幂等及 pending 排斥旧写；其中 demo/socket/protocol fixture 对应协议用例。
- `test_stage12_guided_reading.py:L51-L129,L138-L143`：精确版本/引用、失败无 assistant commit、旧 revision、一次 repair、来源解释不增加作答。
- `test_stage15_visual_context.py:L36-L93`：真实源图片字节绑定、未附图不允许 V 引用、隐私与独立图游标。
- `test_stage15_generation_citations.py:L9-L30`：生成修复不送 private keys、不改 intro/items。
- `test_stage15_rendered_quotes.py:L10-L37`、`test_stage15_alternative_views.py:L119-L161,L270-L310`：窄格式匹配、主/替代视图计数、失败不消耗游标、版本与用户隔离。
- 前端 exact ack 与草稿隔离见 `stage3-student.test.tsx:L112-L259`。

**不可清理**：guided migrations/state/request plans、历史 raw messages/revisions、可选练习记录、所有授权 edition/material revision/image、两个学习 API 的注册、学习门面与 scope helper。`plan_json` 为失败精确重试冻结 detail/state，不能当普通缓存随手删。教师明确 Reset 的 scoped 删除与全局清理是不同操作。

**可评估冗余但本次未删除**：长 prompt 中重复行为规则、旧文档重复导航说明、测试 harness/历史 Stage 标题。它们的教学协议、兼容或验收价值必须先验证；不按文件名或“已有新版”判死代码。跨刷新草稿的旧 answer/ask key 仍由 SavedResponses 读取（`SavedResponses.tsx:L64-L74,L196-L208`），不能在“迁移完成”猜测下清空。
