# 项目协作约定

- 前端为 Vue 3 + TypeScript；业务后端为 Spring Boot + Spring AI + MyBatis-Plus，数据库使用 MySQL。文件格式解析在 Java 进程内完成；PDFBox 处理 PDF，POI 处理 Office，千问通过硅基流动读取图像。Python 仅用于可选的旧数据库导出，不参与当前请求链路。
- 本项目固定使用 Java 17；编译目标、开发启动和容器构建及运行均使用 JDK/JRE 17，不自动改用其他 Java 主版本。
- 当前开发分支为 `cys`。首页支持“中文”和“English”，默认中文。界面语言与课程内容、AI 教学语言分别管理。
- 前端入口：`frontend/src/main.ts`、`frontend/src/vue/ClassroomApp.vue`；接口契约：`frontend/src/classroom-api.ts`；Java 代码：`server/src/main/java/cn/aicademiya`。
- 调度入口在 config/BackgroundJobs；MaterialService 管理材料状态，DocumentParser 只做格式处理，AiService 管理提示与结果，integration/QwenClient 负责模型协议、重试及响应完整性。解析失败或截断的材料不能用于生成或发布任务。
- Service 保留 IService、ServiceImpl；Mapper 继承 BaseMapper。查询和更新优先使用 Lambda 条件构造器。同一实体业务集中处理，避免无价值的抽象层。
- Java 类名使用大驼峰，属性、方法和接口 JSON 字段使用小驼峰；数据库字段使用下划线，通过 MyBatis-Plus 默认规则映射。使用 Lombok 和 Hutool JSON。
- 学生接口与学生预览必须使用公开内容投影，不能包含内部提示词、参考答案及解析。教师手动确认完成，不自动给出正式成绩。
- 发布版本不可被草稿修改覆盖；作答、对话及监控必须绑定明确的任务版本。
- 保护原课程材料、数据库、上传文件和本地配置。迁移先只读导出，导入仅允许空的 MySQL 应用数据库。
- 在 Windows 下通过 PowerShell 7 操作。不启动代理，不修改共享模型服务，不输出密钥。
- 不自行提交、推送、调整版本号或扩大验证范围。是否编译、启动、测试，以用户当次授权为准；不新增测试类。
- 删除和清理仅将明确授权的文件移入 `C:\Users\user\Desktop\智能体回收站\垃圾桶`，不永久删除。不另行生成交付报告。
