# 02｜课程版本、内容编排与教师工作台模块审阅

## 1. 结论与核验范围

审阅日期：2026-10-14；项目根 `D:/HermesProjects/EDUC7703`。下文路径均相对于该根，短模块名均指 `app/backend/aicademiya/`。

- 课程内容采用**草稿→不可变edition→版本化学习run**的数据流；开放时间、成员、staff和回收站独立运行。
- 恢复旧edition会恢复内容并发布新edition，保留原快照、session身份与学生run；课程trash即时关闭本课程内容和历史访问。
- TeachingProfile兼容旧内容规则；指令编译、来源审阅与指令导入预览各有明确作用。受管教师试聊以“本人＋session＋preview generation＋已保存revision”隔离。
- 优先复核Link提取期间的全库写锁、多查询预览的一致性，以及session删除标记与edition restore的组合状态。

**核验范围与证据等级**：`source static`为本次源码阅读，`tests asserted`为已读测试断言，`documented historical`为既有部署记录。当前基线为Stage16 R4/API0.11.0/schema9，见 `app/DEPLOYMENT_STAGE16_RESULT.md:5-24,26-74`。父级补充现场确认CT255 running、current指向R4、`aicademiya.service` active（PID4165）、私有IP `192.168.32.55:18773/api/health`正常；监听绑定私有IP。

本文读取14个课程主模块、相关装配/材料/迁移依赖及测试；guided_engine、AI供应商和解析内部由其他模块报告承担。本子任务新增报告/覆盖清单，未启动应用、运行测试、访问运行库/私有配置或执行模型、网络探测、SSH、迁移及清理。实际浏览器、模型/worker、发布包与本地源码一致性、资源引用闭包和并发影响由父级统一验收。父级本轮全量后端1364通过/1跳过，当前seed启动及隔离备份恢复通过；总结果见上层verification.md。精确范围见 `docs/project-review-20261014/evidence/backend-review-coverage.json`。

## 2. 用户入口与领域边界

| 入口 | 当前后端含义 |
|---|---|
| Course Home / Course actions | 创建、修改课程草稿元数据；Move to trash / Trash / Restore course为运行态回收站。 |
| Home Session卡片编辑/删除/恢复 | PATCH编号/标题/描述；DELETE仅从当前草稿可恢复移出；恢复同ID，不自动publish。 |
| Teaching setup | 保存目标、Additional instructions、reference eligibility、TeachingProfile；compiled preview允许未保存指令overlay。 |
| Questions & answers | 题组/题目/参考答案/材料及Link关联；审核worksheet import后append/replace保存草稿。Stage16复用已有Material的入口另由worksheet_materials注册，本报告只审阅共用提交接线。 |
| Course materials / Session Materials | 课程内唯一文件身份＋多session关联；同一原件共享草稿属性，移除关联不删除课程原件和历史edition。 |
| Publish & versions | 版本列表、详情、差异、发布、恢复为新edition；课程授权来自显式有效staff，不来自全局Admin身份。 |
| 私有Preview / Instructions & source review | 看已保存教学revision、显式reset本人试聊、检查实际来源筛选和静态编译；未保存overlay不改已保存题目与来源。 |
| Student work / History / Export | staff按版本查看、确认/退修学生work；学生仅本人的已发布run/历史。独立History索引能找到当前课程草稿已移除的旧session。 |

名称依据 `app/README.md:9-27,60-69`。实际路由：`main.py:281-302,352-405`、`authoring.py:249-261,291-337,491-531`、`learning_routes.py:31-107,243-316`。

## 3. 源文件职责清单

| 文件 | 职责、关键函数与行号 |
|---|---|
| `app/backend/aicademiya/db.py` | 基础schema、连接/FK/WAL、顺序迁移、一次性catalog导入、初始账号claim；`99-229`。基础SCHEMA不是最终schema。 |
| `app/backend/aicademiya/migrations.py` | Stage2真实旧schema重建、复合learning key、baseline edition及不可变触发器；`5-100`。 |
| `app/backend/aicademiya/versions.py` | draft_snapshot/snapshot/changed/publish/restore、脱路径比较与稳定ID差异；`11-132`。 |
| `app/backend/aicademiya/version_context.py` | course/session鉴权、edition选择、运行开放时间、只读历史、观察学生版本、动态人数；`20-165`。 |
| `app/backend/aicademiya/course_lifecycle.py` | additive课程trash、允许trash元数据的staff鉴权、禁止pending时trash、恢复同课；`9-110`。 |
| `app/backend/aicademiya/session_lifecycle.py` | `in_draft`与meta删除标记，幂等移出及恢复；`8-45`。 |
| `app/backend/aicademiya/authoring.py` | 草稿内容完整性、来源/题图归属、课程材料关联、版本API、私有预览与worksheet审核提交；`50-141,170-243,246-531`。 |
| `app/backend/aicademiya/teaching.py` | 有效TeachingProfile及纯文本教学框架编译；`5-34`。 |
| `app/backend/aicademiya/teacher_preview.py` | 已保存revision hash、preview身份、reserve/commit/legacy guard、本人reset；`10-111`。 |
| `app/backend/aicademiya/teacher_workbench_routes.py` | preview查询/reset、source-review、临时指令提取预览；`13-61`。 |
| `app/backend/aicademiya/source_review.py` | 已保存来源选择＋未保存指令overlay、片段预算/真实材料ID/私有参考、警告；纯只读；`14-115`。不是document source correction写入端点。 |
| `app/backend/aicademiya/models.py` | Payload extra禁止、TeachingProfile序列约束、题组/题目、课程/课次、preview/review/import DTO；`82-258,287-289,337-362`。 |
| `app/backend/aicademiya/services.py` | allowlist公开投影、题目路径、workspace/answer/revision/message持久化、版本只读原因；`13-188`。 |
| `app/backend/aicademiya/learning_routes.py` | 版本化History、workspace、同步保存/提交/参考、旧chat accepted-run提交、staff观察/审核/导出；`21-316`。本报告不替代guided路由审阅。 |
| `app/backend/aicademiya/main.py`（关联） | 实际注册API0.11、课程/课次创建与PATCH、材料上传/解除关系；`97,281-302,352-464`。 |
| `app/backend/aicademiya/material_library.py`（关联） | 文件属于课程、session多对多关系、一次性回填及触发器、同课约束；`9-87`。 |

账号与staff内部安全机制见第一份报告 `01-accounts-security.md`。`is_staff()`检查全局角色，具体课程授权由`course_access`继续完成。

## 4. 从草稿到edition再到学习run的数据流

### 4.1 初始化与持久化结构

`Database.initialize`先创建历史基础表，接着依次执行material-library、Stage2、guided、teacher-preview、course-trash、account-features、staff和document迁移。catalog仅在 `meta.catalog_imported`不存在时导入；不会因重新生成catalog而覆盖已编辑课程。初始Admin只claim未分配seed；新课程显式建立创建者assignment。

- `courses`：当前草稿code/title/description、primary owner、join code和当前 `published_version_id`。
- `sessions`：稳定ID、草稿content_json、`in_draft`，另列保存active/starts_at/ends_at。
- `course_versions`：id/course/number/label/created_at/created_by/snapshot_json；更新和删除由触发器拒绝。
- `materials`：保留来源session_id、原件路径和草稿属性；`material_courses`归属课程，`session_materials`表示当前草稿关联；后者有同课约束。
- `workspaces/attempts/revisions/messages/chat_requests`：以session＋user＋version为作用域。workspace及请求有复合键；attempt再加question；teacher draft用空version，学生run绑定非空edition。
- `teacher_previews`：session/user复合主键，存preview_id/revision/bound_at；不是学生学习数据。
- `course_trash`保存课程运行态关闭；`meta.session_trash:<sid>`保存本次手动课次移出信息，不是物理删除账本。

证据：`db.py:103-190,205-219`、`migrations.py:5-24,40-100`、`material_library.py:9-53`、`teacher_preview.py:17-22`、`course_lifecycle.py:9-22`、`session_lifecycle.py:8-45`。最终schema9由最后的 `document_storage.py:25-52`决定，局部迁移仍出现旧PRAGMA不等于完整初始化倒退。

### 4.2 保存草稿、题目来源与私有字段

`PATCH session`在写锁中调用 `apply_session_update`：

1. 经 `session_access`复核实时账号和课程staff，确认session仍在当前草稿。
2. 把active/starts_at/ends_at从课程内容中剥离，校验时区时间与开始/结束顺序；内容字段不接受null。
3. 校验组/题ID唯一、有意义标题/题干、question.group_id存在、参考答案ID属于当前题目；最多200组/1000题。删题且没明确给新reference map时，自动移除已删题对应参考。
4. 题目source_material_ids必须属于当前session有效关联；source_links经规范化并复用同课现有Link。题图必须是已有合法图片或当前session授权asset，不允许随意外链和未审核asset_key。
5. Link输入与显式材料勾选分开保存；不因添加URL静默勾选材料。无历史引用的managed Link被取消最后关联时只detach，课程库原记录保留。
6. 写入当前session草稿，再返回教师allowlist投影；不自动publish，不改旧edition。

证据：`main.py:389-394`、`authoring.py:50-141,144-167`。测试断言：`app/backend/tests/test_stage2_authoring.py:29-113`。

学生投影的 `instructions`为空，reference_answers和完整TeachingProfile仅教师可见；题目来源内部ID/Link映射不下发学生，图片输出只留label/url/alt，版本图片URL带version_id。学生材料还受visibility/answer_key过滤；不是直接返回catalog JSON。参见 `services.py:46-94`；私有指令测试 `test_private_instructions.py:7-33`分别断言学生投影过滤和服务端教学请求使用私有指令。

### 4.3 发布、差异与恢复

`draft_snapshot`读取所有 `in_draft=1`的session和其实际材料关联；去掉运行开放字段及内部下划线字段，保存课程元数据、题组/题目/参考/TeachingProfile、材料元数据和存储绑定。快照可以含status=draft的课次；**学生读取另外要求课次在该edition中status=published**，因此把课次标为published与创建课程edition是两层操作。

`publish`在API写锁下分配课程内递增number，生成新ID，插入快照并更新课程指针。已关联的完整文档没有可用document revision时返回409；未关联课程库文件不阻塞，带旧可用revision的失败重试不自动阻塞。该门槛检查版本与资源绑定。

`diff`先移除不适合UI的文件路径/内部文档信息，再递归比较；按ID定位列表项，保留顺序变化提示。它比较的是当前草稿与指定旧edition，不是学习答案差异。

`restore`读取旧快照并深拷贝：使该课queued/running文档任务失效；恢复课程元数据；全部session先设in_draft=0，再恢复选中快照的session及关联材料。每个共享Material仅恢复一次；没有全局归档未选中文件。最后再publish一个新edition。原session关系身份、旧快照、已存run及文件不删除，运行开放时间列保持原值。

证据：`versions.py:8-107,110-132`、`authoring.py:301-337`、`version_context.py:51-68`。测试断言：`test_stage2_versions.py:26-63,86-118,144-162`。账号、成员和服务设置独立保留。

### 4.4 学生与教师选择edition

- 每次course access先实时校验actor；staff必须有有效assignment，学生必须有enrollment。trash统一410；到期成员历史也不可继续读。
- staff省略version_id读取当前草稿，removed session返回404；显式edition读取不可变快照。学生省略值读取当前发布版；空字符串version_id是422。
- 学生读旧edition或归档成员时，必须已存在本人对应workspace；不能只知道版本ID就浏览从未开始的旧课程内容。写入旧edition/归档成员/未开放session被拒。
- 已有其他edition学习记录后，省略version_id的写请求返回409要求刷新带版本，阻止旧页面写入新edition。参考答案、消息、revision、request ID和提交均沿同一version键定位。
- 开放时间优先于manual active：只要有start/end就按区间，开始含边界、结束不含边界。关闭不删除已有历史；已接受旧chat可在关闭/发布后完成原run，但commit必须再验证课程和actor权限，不能借此越过撤权。
- History枚举本人workspaces，不依赖当前session列表；staff变Student时跳过其空version私有试聊。教师观察学生默认选择其最近非空version；若无已存run可选择当前发布版并建立空workspace。

证据：`version_context.py:20-110,113-165`、`learning_routes.py:21-77,109-202`。测试断言：`test_stage2_versions.py:26-118,129-179`、`test_stage11_accounts_staff.py:182-220`、`test_stage11_revocation.py:69-112`。最后一组使用mock/demo受控撤权fixture。

### 4.5 提交、教师确认及GET的实际副作用

`save_answer`保存当前答案并追加revision；修订不覆盖旧revision。submitted/confirmed通过 `editable`锁定，needs_revision继续允许修改。显式submit要求已选reading且当前有效题目都已有答案；教师review只接受submitted/confirmed/needs_revision，写对应version的note与review时间。形成性充分反馈、回答数和教师正式确认是不同状态。

`workspace_response`内部会 `ensure_workspace INSERT OR IGNORE`；workspace GET、export GET、教师观察/列表也可能首次建立空operational workspace，并使用写事务。**“不调用模型/不改内容”不能写成“所有GET都零DB写入”**。独立preview identity GET与source-review则没有这类初始化写入。

证据：`services.py:97-141,144-188`、`learning_routes.py:73-107,243-316`、`teacher_workbench_routes.py:14-30`。老JSON export路由只返回JSON，HTML/TXT transcript由其他路由实现，不把README列出的全部格式算作本文件已覆盖。

## 5. 课程/课次生命周期的不同含义

### 5.1 课程Move to trash

已分配staff可查看trash课程元数据/计数并恢复，普通内容路径不提供allow-trashed开关。入trash前在同一writer reservation检查本课程任意用户、任意edition的chat/tutor pending；有未完推理则409。成功仅增加 `course_trash`行；邀请码、课程/课次/材料/学习内容均保留。课程普通列表、History、教学、材料、版本等即时关闭；无关课程不受影响。

恢复仅删该标记，不publish、不轮换邀请码、不改开放时间、不改独立成员/账号保留期限。账号保留期清理暂缓而不是延后期限；恢复后可能立即符合到期清理条件。

证据：`course_lifecycle.py:30-110`；测试断言：`test_stage8_course_lifecycle.py:164-279,282-408,412-521,621-681`。回收站“metadata count”是保留的关系统计，`material_count`不是只数当前关联文件；`enrollment_count`也不是只数活动Student，与实时 `student_count/admin_count/teacher_count`含义不同。

### 5.2 Session Delete

`DELETE /api/sessions/{id}`校验staff和live course，写 `meta.session_trash:<id>` 的removed_at/removed_by并设in_draft=0；重复删除相同marker幂等。没有DELETE sessions/materials/workspaces的SQL，也没有物理文件删除。关联仍在表里，只是在当前草稿投影中隐藏，所以Restore可复原本session材料关联；历史published edition继续保留，学生看到新的移除结果需要显式publish。

“Deleted sessions”只显示in_draft=0且有显式删除marker的行；因恢复旧edition而不在草稿、但没有手动删除marker的session不一定显示在该回收站。恢复同ID不自动发布。源代码风格较紧凑，但不能因此认为是无用stub删除。

证据：`session_lifecycle.py:8-45`、`material_library.py:48-72`；测试断言：`test_stage16_sessions.py:5-38`、`test_stage11_accounts_staff.py:119-128`。

## 6. 教学框架、私有试聊与来源审阅

### 6.1 TeachingProfile与编译

`models.TeachingProfile`固定schema_version=1；限定warmup/worksheet/quiz/reading/wrap_up的唯一顺序，worksheet必须存在、wrap_up必须最后，quiz/reading只能在worksheet后。reading问题1–5；idle_hint_seconds为0或10–300；presentation=full/paced。新session默认 `after_sufficient_answer`，已有内容无profile时通过 `effective_profile`返回 `on_request`，不回写旧JSON。

`compile_teaching`纯函数生成role/goals/background/student profile/strategies/tone/feedback/phases/reading/references/additional章节和warnings；只读预览可覆盖未保存指令/目标/语言/参考资格。**参考“是否有资格展示”与“何时主动送出”分开**；编译文本也明确应用而非模型负责正式展示、提交或教师确认。源码文本不是模型必定遵守的证据。

证据：`models.py:101-134,189-224`、`teaching.py:5-34`、`main.py:368-380`、`authoring.py:291-299`。测试断言：`test_stage3_guided.py:84-119,322-331`；相关测试的读取范围列在覆盖清单中。

### 6.2 preview generation与saved revision

`teacher_preview.saved_revision`按已保存instruction/目标/题组/题目/参考/有效profile/材料内容和稳定选择顺序做SHA-256。排除开放时间、原件路径等不属于教学内容的字段；有意义的保存变化使受管preview stale，页面仍可读旧记录但后续写入409。

`preview_info`不会自动采用/重置旧试聊；存在legacy trial时给reset_required。显式reset先核对expected_revision且拒绝pending；仅按当前staff本人、该session、空version顺序删除本人的试聊learning行并换新preview_id。其他staff、学生、其他session、已发布run不受影响。

受管preview在reserve与commit核对generation/revision；同步reading/answer/reference reveal/submit要带query preview_id，旧chat endpoint不能用它绕过受管限制。未受管旧教师API保留兼容路径，并不是所有历史教师工作都已自动绑定新版preview。

证据：`teacher_preview.py:10-111`、`teacher_workbench_routes.py:14-25`、`learning_routes.py:21-29,79-118,204-255`。测试断言：`test_stage6_preview.py:35-113,116-219,260-308`、`test_stage6_full_preview.py:8-60`。

### 6.3 来源审阅、预算与指令文件

- `source-review`取已保存题目和已保存session材料关联；未保存overlay只改编译指令，不假装保存题目/来源已变。worksheet按当前题目source IDs/URL筛选，optional阶段用session公共池。
- `selected_tutor_materials`先剔除answer_key和teacher-only worksheet全文，保留当前题目私有reference独立传递。其他私有知识可用于worksheet选中证据，但optional quiz/reading排除私有证据与worksheet参考。
- 报告返回实际Material ID、selected/included、available_chars/included_chars、排除原因和warning；重复title/source_label不能替代ID。legacy excerpt预算public32,000字符/private8,000，整体live request容量60,000 UTF-8字节；`request_bytes`是上限，不是一次完整实际请求测量。
- 完整document只在这里呈现存储revision/质量和可读字符摘要；不跑model read planner，不声称全部页面进上下文。它与document source correction API不是一回事；
- instruction-import先验证课程授权和25MiB/格式，随机临时目录在数据目录下提取后删除，再复核权限；返回文本/覆盖说明。超过30,000指令字段上限明确警告，并不静默裁成可保存内容；真正保存仍需显式PATCH，真正学生变更仍需publish。

证据：`authoring.py:214-243`、`source_review.py:14-115`、`teacher_workbench_routes.py:32-61`。测试断言：`test_stage6_source_review.py:69-140,144-195`、`test_stage6_instruction_import.py:31-153`。后者包含本地CPU OCR合成用例。

## 7. 外部依赖与并发边界

- 普通课程/版本/权限操作依赖FastAPI/Pydantic、stdlib SQLite/JSON/时间/hash；无远端课程数据库。事务由 `Database.connect`提交/回滚并关闭，FK启用、15秒锁等待。
- 课程Link创建/编辑和题目新增Link可调用 `link_materials.extract_link` 的HTTP/DNS/内容解析；失败保留可用URL及明确error/warning，不假造已读原文。教学编译、source-review不触发该重抓路径。
- 轻量指令导入调用本地材料extract入口，依赖PyMuPDF、Office/图片/CPU OCR相关包；worksheet可选模型、完整文档worker均属于外部模块，本报告只记录调用/版本绑定边界。
- 关联/版本恢复必须保留原件、asset目录和document revision绑定；恢复备份涉及路径重定位，不可只拷SQLite然后宣称材料可用。

证据：`db.py:103-112`、`authoring.py:21-47,339-384,426-485`、`teacher_workbench_routes.py:32-61`、`link_materials.py:184-252`；依赖清单 `app/backend/requirements.txt:1-13`。恢复断言见 `test_stage8_course_lifecycle.py:567-616,707-744`和`test_stage6_preview.py:289-308`。

## 8. 审阅时的历史文档差异

父级已纠偏README/AGENTS当前入口，原版保留于文档备份。下面的Stage15残留记录描述审阅时状态。

1. **授权术语已变**：文件标题、函数名owner_metadata及部分测试名仍写owner-only，实际均经assigned staff；`app/STAGE11_CONTRACT.md:9,17,21-24`和`app/CONTEXT.md:4-9`才是该语义的明确解释。历史owner是primary责任身份，不是备用权限。
2. **新session/旧profile不同**：`models.py:111`的默认自动对照不能直接覆盖旧edition；兼容逻辑在 `teaching.py:5-10`。不能用“统一默认值”批量回填历史教学规则。
3. **课程trash、session删除、材料detach、edition restore各自不同**：分别为运行态关闭、草稿成员移出、共享文件关系移除、内容恢复并新发布；README的“保留”不意味着运行访问仍开放。
4. **Stage16当前、Stage2/6/8/11命名是演化层**：旧文件不是独立废弃实现，仍被当前 `main.py:153-160,396-405`注册。`app/README.md:31,98,106`仍有Stage15“最新”/release残留，应与Stage16部署文档分层看待，不以旧条目判断当前线上版本。
5. **只读预览不是完整live request**：source_review自己的warning明确区分capacity、静态片段、saved sources、未保存overlay与live planner；不能把页面上的字符数转述成模型已完整读取整份文件。

## 9. 问题与建议

优先级沿用第一份报告，表中分别列出源码事实与所需验证。

| 优先级/性质 | 具体问题及建议 | 证据 |
|---|---|---|
| P2｜静态事实，影响待测 | 部分外部Link提取位于SQLite `BEGIN IMMEDIATE`内部：PATCH session新增来源调用link_data，PATCH Link也持锁抓取。一个慢公共站点或多Link可能延长全库写锁，影响登录/改密/归档/发布；客户端已有超时。建议把网络提取与写锁分离，并在落库时复核当前草稿/来源/权限；不要无依据扩大成通用job框架。 | `main.py:389-394`、`authoring.py:73-141,350-384`，特别`121,371`；实际HTTP入口`link_materials.py:194-235`；DB超时`db.py:105`。 |
| P2｜一致性建议，未复现 | version列表/详情/diff与preview identity/source-review使用多条SELECT，但部分没有显式`BEGIN`统一读快照；并发保存或publish时可能组合不同瞬间的current pointer、changed、revision及材料。关键写入仍由写锁与generation保护。建议用一个定向并发读用例决定是否增加read transaction。 | `authoring.py:301-330`、`teacher_workbench_routes.py:14-30`、`source_review.py:27-115`；对照已有同快照History `learning_routes.py:36-38`。 |
| P3｜静态交叉状态，待确认产品语义 | edition restore改 `in_draft`/重建材料关系但不处理 `session_trash:<sid>` marker。手动删除→恢复含该session旧版→再恢复不含它的版时，旧removed_at/removed_by仍可能出现在Deleted sessions；建议补一个组合用例并明确删除元数据是否需要保留/失效，不直接删meta。 | `versions.py:75-91`、`session_lifecycle.py:19-22,29-45`；已读`test_stage16_sessions.py:5-25`未覆盖与多次edition restore组合。 |
| P3｜静态DTO差异 | SessionCreate.number只有ge1，SessionPatch.number另有le9999；可创建编辑端随后无法以同一数值保存的编号。建议统一编号边界或说明兼容意图。 | `models.py:137-143,189-194`、`test_stage16_sessions.py:27-31`。 |

账号归档后变staff的课程保留期范围问题见第一份报告第7节，避免在此重复记为第二个事故。

## 10. 不可清理文件与可清理建议

### 不可因“旧stage/已删除/无当前关联”而清理

- 所列运行模块及历史迁移、schema标记、不可变版本触发器、材料同课/自动入库触发器；它们是当前初始化/授权链的一部分。
- `course_versions`、移出草稿session、其workspaces/答案/revisions/messages/requests、前staff私有preview和teacher_previews绑定。
- 课程库未关联文件、历史edition引用的原件/题图/document revision、旧release中仍被保存路径引用的文件。
- 未过期worksheet import暂存、关联asset目录及完整document jobs/revisions；仅删除staging行不等于可判断磁盘目录无引用。
- 原始catalog/私有材料与来源谱系、受限配置、HMAC namespace、可恢复备份和失败证据；本轮不读取/打印秘密值。

### 仅建议，未执行清理

1. 父级统一做“当前草稿＋全部edition＋pending import＋document revision”的资源引用清单，再判断文件候选；不能以当前session_materials集合当全站保留集。
2. 将重复的历史验证产物按stage/候选/最终结果建立索引，先保留失败原因与最终证据。老测试应按现契约补注释，不因test_stage2/6命名直接删除。
3. 可再生成缓存与不再引用的解包候选应由父级资源清单决定；本报告不授权删除任何运行数据、迁移、源码或旧部署包。
4. 当前README/注释里owner与Stage15残留可另次授权整理；本轮只写新报告，不替换已有项目文档。

