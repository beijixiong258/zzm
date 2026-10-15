# 01｜账号、课程授权与HTTP安全模块审阅

## 1. 结论与核验范围

审阅日期：2026-10-14。项目根为 `D:/HermesProjects/EDUC7703`，下文证据路径均相对于项目根；行号对应本次读取的源码。

- 平台账号、全局角色、课程staff、学生enrollment各有独立关系。**课程教学权限来自显式、有效的 `course_staff`**；Admin的全局账号管理权与课程教学权分开，`owner_id`记录主负责人。
- 核心账号/staff写入在 `BEGIN IMMEDIATE` 内复核角色、账号状态、会话及管理人员连续性。全局导入采用hash-only暂存、原子提交和限时结果恢复；课程名单导入保留提交后删除暂存的协议。
- 安全中间件落实Host、跨站写入、实际body大小、缓存/防嵌入响应头与单进程节流。需要优先核验本人写入的并发撤权窗口、跨角色保留期和课程名单的未知响应恢复。

**核验范围与证据等级**：`source static`表示本次源码阅读；`tests asserted`表示已读测试断言，执行结果由父级统一提供；`documented historical`表示既有部署记录。部署基线为Stage16 R4/API0.11.0/schema9，见 `app/DEPLOYMENT_STAGE16_RESULT.md:5-12,61-74`。父级补充的现场只读核验确认CT255 running、current指向R4、`aicademiya.service` active（PID4165），私有IP `192.168.32.55:18773/api/health`正常，服务绑定私有IP。

本子任务读取24个主模块及关联文件/测试，新增报告与覆盖清单；未启动应用、运行测试、读取运行库/私有配置或执行模型、联网、SSH、迁移与清理。浏览器行为、真实配置/worker数、依赖漏洞和生产资源引用留给父级验收。父级本轮全量后端1364通过/1跳过；完整前端、构建、远端回读和定向复现见上层verification.md。精确文件与已读范围见 `docs/project-review-20261014/evidence/backend-review-coverage.json`。

## 2. 作用与用户入口

| 用户入口 | 实际能力及后端边界 |
|---|---|
| Login / Register | 邮箱密码登录；自助注册只能创建Student，须注册开关开启且邀请码属于未入回收站的课程。旧账号登录不重新套用新密码创建规则。 |
| Settings → Account | 改本人显示名、凭当前密码改密、上传/删除本人头像。临时密码用户先完成改密，`/auth/me`、改密与登出等例外仍可用。 |
| Settings → Global User Accounts | Admin搜索/筛选/创建各角色账号、显式改角色、停用/恢复、CSV/XLSX审核导入；不是课程教学内容总入口。 |
| Course staff assignments | Admin可查看所有课程的轻量元数据及staff分配；只有已分配staff才可操作相应课程教学内容。Teacher可查看所分配课程同事但不能授权同事。 |
| Course Students / Learners | 已分配Admin/Teacher管理该课程的Student：新建或关联已有Student、导入、移出及恢复；不是修改全局角色或他课成员。 |
| Settings → Feedback | 各角色提交并查看本人Bug/Idea/General；Admin另有全局人工收件箱、回复、New/Reviewed状态。Reviewed不是解决承诺，代码未接邮件发送。 |

入口名称来自 `app/README.md:25,39,43-58`；后端依据：`app/backend/aicademiya/main.py:134-190,222-279,304-350`、`course_staff.py:108-160`、`global_accounts.py:81-139`、`feedback.py:89-153`（这些短文件名在下文均指同一后端目录）。

## 3. 源文件职责

| 源文件 | 已读职责与证据 |
|---|---|
| `app/backend/aicademiya/auth.py` | 进程内滑动窗口限流、未知/归档账号dummy密码校验、cookie令牌hash查询；`14-67`。 |
| `app/backend/aicademiya/access_control.py` | 现有settings表中的注册开关；严格布尔DTO、管理员读写、写锁后重新校验会话；`10-47`。 |
| `app/backend/aicademiya/http_security.py` | ASGI早期Host/CSRF/Content-Type/body字节边界、认证IP节流、API私有缓存及浏览器响应头；`13-119`。 |
| `app/backend/aicademiya/course_staff.py` | staff/additive导入表迁移、一次性owner回填、实时actor鉴权、显式assignment与primary连续性及管理API；`9-160`。 |
| `app/backend/aicademiya/global_accounts.py` | 账号公开投影、最后可用管理员保护、角色变更/会话撤销、可逆停用、全局列表及CRUD；`9-139`。 |
| `app/backend/aicademiya/account_import.py` | 混合角色审核导入、账号假设快照、hash-only暂存、原子commit、精确结果GET恢复；`13-141`。 |
| `app/backend/aicademiya/roster.py` | 课程及旧全局Student名单、批量归档恢复、受限CSV/XLSX读取、课程导入、到期维护；`16-344`。 |
| `app/backend/aicademiya/account_avatars.py` | 真实解码、静态图像约束、去元数据重编码、DB BLOB、鉴权头像读取；`18-92`。 |
| `app/backend/aicademiya/account_features_migration.py` | 增加avatars/feedback表及约束，savepoint回滚；`4-30`。 |
| `app/backend/aicademiya/feedback.py` | 本人Feedback归属、持久请求标识、分页一致性、管理员乐观revision人工回复；`16-153`。 |
| `app/backend/aicademiya/main.py` | 实际路由装配、鉴权依赖、脱敏异常、登录/注册/改密/姓名/单个建号；重点`106-190,222-350`。 |
| `app/backend/aicademiya/db.py` / `models.py` / `config.py` | 密码与会话存储、公开User；账号DTO与密码规则；HTTP Origin/Host/Secure配置。`db.py:24-36,232-246`、`models.py:7-79,315-334`、`config.py:8-78`。 |

关联课程权限与版本保护见第二份报告 `02-course-authoring-versions.md`。

## 4. 具体数据流

### 4.1 登录、临时密码及会话撤销

1. ASGI先检查Host/跨站信号/请求体；登录另受IP桶和规范化邮箱账号桶限制。邮箱去首尾空白并小写用于查询，密码保持字面内容。
2. 登录取得SQLite写锁后查询非demo账号，执行真实scrypt校验；不存在账号或无hash时也做dummy校验。失效/归档账号拒绝签发。
3. `issue_session`生成随机token，库里只存SHA-256 token hash和30天到期时间；cookie使用HttpOnly、SameSite=Lax，Secure由实际scheme或显式配置决定。
4. 鉴权先查实时账号及有效会话；`current_user`再拦截强制改密。内部 `AuthenticatedUser.token_hash`不是公开JSON字段，事务内 `live_actor`可用它再次验证会话，阻止旧角色变回来后的ABA旧会话绕过。
5. 改密在同一写锁下重新验证当前cookie和当前密码、更新scrypt hash、清除该用户所有旧会话并发新cookie，不修改别人会话。新密码要求8–512字符、至少ASCII字母和数字；登录只要求1–512字符，兼容旧密码。

证据：`auth.py:28-67`、`db.py:24-36,232-246`、`course_staff.py:9-13,44-57`、`main.py:188-190,222-270`、`models.py:7-34,71-75`。测试断言：`app/backend/tests/test_auth_change.py:39-61,95-111,137-189,303-380`、`test_password_policy.py:6-21`、`test_stage11_revocation.py:24-40`。

### 4.2 注册开关、建号与角色/课程授权

- 自助注册：`BEGIN IMMEDIATE` → 重新读取 `settings.registration_enabled` → 查询未trash课程邀请码 → 插入Student → 插入enrollment → 签发会话。缺失开关默认允许；存储值不是精确字符串`true`则关闭。开关只管自助注册，不影响已有账号登录、已有Student加入课程或授权staff手工建号。
- 手工建号：单个全局创建仅Admin；课程创建/关联仅该课显式staff。已有Student可不提供临时密码，不覆盖其姓名、密码或状态；新账号必须提供合规临时密码并 `must_change_password=1`。归档成员必须显式恢复，不能通过邀请码悄悄重入。
- 角色变更：Admin不能改自己的全局角色；降下最后可用Admin被拒。staff→Student须先交接primary及移除全部staff关联；角色变化撤销目标会话但保留学习、头像、Feedback。Student→Teacher/Admin不自动获得课程staff权限。
- staff分配：先确认目标是活动Admin/Teacher；移除主负责人前必须显式交接；不能留下没有有效staff的课程，包括trash课程。更换primary不自动移除旧经理。全局Admin查看人员元数据不因此获准下载私有材料。

证据：`access_control.py:15-47`、`main.py:234-247,304-350`、`global_accounts.py:35-78,108-118`、`course_staff.py:94-160`。对应测试：`test_stage10_access_settings.py:67-116,119-173`、`test_stage11_accounts_staff.py:42-94,160-220,224-304`。`ProvisionStudent`对非空临时密码仍先执行字段校验，只有空/省略值走已有账号免密码路径（`models.py:37-47`），不应把注释理解为忽略任何错误密码输入。

### 4.3 两套名单导入协议

| 维度 | 全局Account import | 课程Roster import |
|---|---|---|
| 权限/作用域 | 实时Admin + owner/import ID | 显式course staff + owner/course/kind/import ID |
| 输入 | CSV/XLSX，name/email，role可覆盖default role，temporary_password可用默认值 | CSV/XLSX，name/email/temporary_password，不接受role列 |
| 操作 | 新建或同角色skip；不同角色报错，不批改旧账号 | create / enroll / restore / skip；已有staff/全局归档账号报错 |
| 预览 | hash-only暂存30分钟；每Admin最多30个pending | hash-only暂存30分钟；每owner/kind最多30个未过期roster预览 |
| 提交 | 先核对每行账号假设，再全部插入；记录精确`user_ids`；提交后清除暂存hash | 先核对分类/账号ID/成员归档状态及期限，再全部写入；返回计数，随后删除暂存 |
| 未知响应恢复 | GET原import，pending/committed及原结果；committed保留24小时；重复commit返回同一结果 | 没有同等持久结果GET；成功后同ID不再存在，不能把重发404当未写入 |

两者都限制原文件2MiB、1000数据行；XLSX在openpyxl之前走实际ZIP解压防护，再检查目录/行列边界。全局导入显式拒绝公式；课程路径使用data_only读取，不应宣称两者的公式处理完全一致。

证据：`account_import.py:24-114,117-141`、`roster.py:115-180,183-278`。测试断言：`test_stage11_import.py:36-72,118-140,143-230`、`test_stage10_roster_security.py:11-45`、`test_stage2_accounts.py:182-233,262-275`。全局创建账号不自动插入staff或enrollment，测试在 `test_stage11_import.py:63-72` 明确断言。

### 4.4 头像与Feedback

- 头像：上传最多5MiB → Pillow识别真实PNG/JPEG/WebP且单帧 → 在完整像素load之前检查1600万像素边界 → EXIF旋转、居中256×256裁剪 → 新像素图重编码PNG、输出最多512KiB → BLOB和digest写入 `account_avatars`。不保存用户文件名、原图或EXIF/ICC/text元数据。读者须有效登录且已改密；可读取其他活动账号的头像，但须精确当前digest。它不是私有课程资源，也不是匿名公开URL；替换后旧版本URL返回404。
- Feedback：服务端绑定author ID，按 `(author_id,request_id)`唯一；同请求相同规范化正文返回已有记录，不同内容409。本人详情/请求GET不可读取他人；Admin必须走独立inbox。人工回复要求 `expected_revision`，写锁下复核Admin及revision；并发旧revision返回409。作者展示来自当前活动账号，归档/删除后可显示null；正文并非跟着作者删除。

证据：`account_avatars.py:24-92`、`account_features_migration.py:7-24`、`feedback.py:49-153`。测试断言：`test_stage9_account_avatars.py:44-89,105-182,217-226`、`test_stage9_feedback.py:72-105,116-148,173-244`。

## 5. SQLite状态、保留期与HTTP安全边界

### 5.1 当前schema的静态状态

以下状态来自当前源码定义。

- `users`保存当前单一全局角色、密码hash、demo标志、强制改密及归档/到期；`auth_sessions`为hash令牌；`enrollments`独立保存课程归档/到期。
- `course_staff(course_id,user_id)`为显式授权，复合主键去重；迁移标记 `stage11_staff_backfilled`确保owner只回填一次。删除授权后重启不会根据owner重新授权。
- `account_imports`保存pending/committed审核与回执；旧 `import_staging`用于课程roster和worksheet，不能因名称相近合并或清空。
- `account_avatars.user_id`在账号删除时CASCADE；`feedback.author_id`在删除时SET NULL，保留意见正文及回复。
- 初始化使用WAL，每次连接启用FK，连接超时15秒。Stage9/11局部迁移中的user_version7/8是历史步骤，初始化最后调用document迁移使最终版本为9；不能只读某个局部PRAGMA就判当前schema是7或8。

证据：`db.py:103-134`、`migrations.py:50-70,84-100`、`course_staff.py:16-41`、`account_features_migration.py:4-30`、`document_storage.py:25-52`。迁移测试断言：`test_stage11_migration.py:34-108,127-152`。

### 5.2 归档不是一种操作

1. 课程移出：只更新enrollment，30天保留；本人原有学习历史可读、不能继续写，其他课程和全局账号不变。
2. **新Global User Accounts停用**：写 `users.archived_at`，`purge_at=NULL`，撤销会话，可逆且不新建自动清除期限；显式恢复清除归档和期限。
3. **旧 `/api/admin/students/archive`**：保留原Student全局30天归档协议，仍可能触发到期物理删除账号及学习行。它不等价于第2项“永久可恢复停用”。
4. maintenance按授权范围删除到期学习表、enrollment或Student账号；共享课程材料、版本和原文件不在该删除列表。guided子表通过workspace外键CASCADE清除。课程trash暂停相应破坏性保留期执行，但不改原期限；恢复后过期内容可能在下次维护被清理。
5. 原staff变成Student后，primary/staff/teacher_preview/trash归属及未到期导入引用会保留其身份，防止FK失败或丢教学溯源。该保护不等于所有课程enrollment清理都被取消。

证据：`roster.py:20-67,89-112,295-323`、`global_accounts.py:62-78`、`guided_migration.py:9-19`；维护在启动及每60秒执行，`main.py:74-86`。测试断言：`test_stage2_accounts.py:105-178`、`test_stage11_retention_roles.py:12-49`、`test_stage8_course_lifecycle.py:621-681`。

### 5.3 HTTP与外部依赖

- 认证JSON上限16KiB，一般JSON4MiB，一般multipart27MiB，课程材料POST multipart66MiB；上传业务仍各自执行头像5MiB、名单2MiB等更小边界。检查累加实际ASGI字节，不只信Content-Length；限制内请求先缓存在内存再重放给路由。
- Host须唯一且被允许；默认允许本机/测试Host和私网IP，精确配置可增允许Host/Origin，不接受通配符。写入显式Origin检查；缺Origin时拒绝跨站Fetch Metadata和外站Referer，同时保留无浏览器信号API客户端兼容性。这不是通用CSRF token方案。
- limiter键是进程随机密钥下的身份digest，容量4096、线程锁保护、容量满fail closed，不信任原始X-Forwarded-*。应用依赖ASGI服务器精确信任反代后提供的peer/scheme；重启清空桶，多worker不共享。
- API通常 `private,no-store`；头像 `private,no-cache`；设置nosniff、SAMEORIGIN、frame-ancestors、same-origin Referer等。CSP主要限制嵌入，**不是禁止脚本的完整CSP策略**；PDF没有套会破坏原生阅读器的sandbox。
- 依赖FastAPI/Starlette、Pydantic、python-multipart、SQLite/stdlib密码学、Pillow图像解码、openpyxl及 `extraction_limits.office_guard`。此账号链路不依赖邮件、OAuth或远程身份服务。依赖清单见 `app/backend/requirements.txt:1-13`；头像模块直接依赖Pillow解码。

证据：`http_security.py:13-119`、`config.py:44-78`、`auth.py:14-45`。测试断言：`test_stage10_security_primitives.py:19-48,76-134,137-190`、`test_stage10_http_security.py:9-148`。公网前置条件仍以 `app/README.md:35-41` 为边界：HTTPS/Secure cookie/反代信任和网络入口限制须另行现场验收。

## 6. 审阅时的历史文档差异

父级已更新本节提到的README/AGENTS入口；旧文原版保存在entry-documents-before.zip，下面保留发现来源。

- `app/CONTEXT.md:3-13`、`app/STAGE11_CONTRACT.md:9,15-27`的显式staff、当前角色计数、primary和账号/课程分离语义与本次代码一致；Stage11文件中的历史授权、分工、部署步骤不构成本轮操作授权。
- `services.py:1`、`course_lifecycle.py:1,31,36`以及部分测试名仍写owner/ownership。实际 `course_access` / `require_assigned` 已改为显式staff，不能按旧注释把协管教师挡在课程外，更不能以owner字段兜底恢复被撤销的权限。
- `app/README.md:9`指向Stage16，但 `31,98,106`仍混有Stage15 release/“最新”引用，不能据此覆盖Stage16 R4基线；建议统一“最新”入口。
- 旧Student全局归档API仍留存，不应从Stage11“Global User Accounts停用不自动purge”推断全部历史API都已改成同一语义。

## 7. 问题与建议

优先级：P1为高影响权限/数据风险，P2为应安排的可靠性或边界复核，P3为一致性/维护项。表中区分源码事实、待复现风险与建议。

| 优先级/性质 | 事实、影响与建议 | 证据 |
|---|---|---|
| P2｜静态事实＋并发待复现 | 头像POST/DELETE、本人Feedback POST和姓名PATCH没有像全局账号/staff写入那样在最终事务内调用`live_actor`或重新校验session。依赖已通过后，若另一个事务撤销会话/停用账号，已排队的本人写入存在继续落库窗口。建议用可控writer屏障核验并统一事务内身份复核。已读头像/Feedback测试只覆盖请求前已归档/强制改密，不能证明撤权竞态已覆盖。 | `account_avatars.py:55-79`、`feedback.py:90-104`、`main.py:134-142,164-168`；对照`course_staff.py:44-57`及`test_stage11_revocation.py:24-64`。 |
| P1｜隔离合成库已复现 | maintenance挑选到期enrollment时不按当前全局角色筛选；`purge_learning(uid,cid)`也不区分已发布学生run与`version_id=''`教师preview。学生被移出课程后，若在原期限前升级并获staff授权，旧enrollment到期可能一并清除其新教师试聊；`teacher_previews`身份绑定本身却被保留。父级使用当前change_role、staff assignment、session access与maintenance在全新合成库复现：教师workspace/messages从1/1变0/0，preview绑定与staff仍存在。建议区分学生run与教师preview保留；证据为 `../evidence/retention-role-reproduction.json`。 | `roster.py:20-25,42-51`、`teacher_preview.py:17-22,99-111`；已读`test_stage11_retention_roles.py:12-49`主要保护账号身份删除，不覆盖此组合。 |
| P2｜协议差异事实 | 课程roster commit成功后删暂存，没有全局导入式committed回执GET。若成功响应丢失，只能独立查看名单/账号当前状态，不能证明原响应，自动重发会得到404。建议保持前端未知写入状态与只读检查，不为统一外观而删掉兼容API或盲目重试。 | `roster.py:250-278,339-344` 对照 `account_import.py:79-114,137-141`。 |
| P3｜文档/命名事实 | owner-only旧注释、README Stage15“最新”及两种全局归档语义易误导后续维护。建议后续统一术语、归档说明与交叉链接。 | 第6节；`roster.py:309-323`与`global_accounts.py:62-78`。 |

## 8. 不可清理文件与可清理建议

### 必须保留

- 本报告列出的运行源码、迁移和安全/并发测试；`course_staff`一次性回填标记、课程人员与主负责人记录不能当缓存重建。
- 活库、关联WAL/SHM及有效备份、installation HMAC secret、私有配置、账号hash和导入暂存/回执。不能通过删库、重放种子或清空auth表“整理现状”。
- `import_staging`不只有名单，可能包含待提交worksheet及原件/图片路径；`account_imports`也可能承担24小时结果恢复。不能脱离期限/归属直接删行或对应文件。
- 归档学习记录、前staff私有preview、头像BLOB、Feedback正文/回复及课程共享原件；是否暂不可访问不等于无引用。
- Stage10/11/16测试证据和失败记录在完成父级证据归档/去重确认前保留；旧stage命名仍承担当前回归保护。

### 仅建议，不执行

1. 由父级统一盘点已不再引用的 `__pycache__`、`.pytest_cache` 等可再生成缓存；先排除正在执行的测试与验收证据，不能把运行数据或原件混入。
2. 把散落在测试目录的历史JUnit XML归入按stage/结果分类的证据索引；失败与最终通过应明确分开。不要只因有新结果就删除失败诊断。
3. 另次授权下整理owner术语与README最新入口，保持旧API/保留期说明；本轮没有删除、移动或改写任何现有文件。

