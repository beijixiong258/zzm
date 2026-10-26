# 前端开发

Vue 3 + TypeScript + Vite，应用版本沿用 0.1.0。开发服务器默认 5173，浏览器直接请求 8001 的业务接口；通过 `VITE_API_BASE_URL` 可指定完整 API 地址。

| 入口 | 职责 |
| --- | --- |
| `app/frontend/src/vue/ClassroomApp.vue` | 登录方式、语言、课程导航及角色页面 |
| `classroom-state.ts` | 账号、课程、导航和未保存修改保护 |
| `app/frontend/src/classroom-api.ts` | 类型契约、HTTP 调用、下载及学生内容投影 |
| `ClassroomHome.vue`、`CoursePeople.vue` | 三项课程设置、班级成员及个人邀请码 |
| `TeacherWorkbench.vue` | 独立教师工具入口、保存资源及复制资源到课程 |
| `TaskEditor.vue` | 材料多选、补充提示词、AI 生成与修订、发布及学生模拟容器 |
| `StudentTask.vue` | 学生页面及教师模拟共用，包含阅读、作答、附件、对话、提交与历史；真实学生可导出自己的学习结果 |
| `TaskMonitor.vue` | 学生进度、作答与对话审阅、AI 反馈审核 |
| `TaskContent.vue` | 学生可见讲义、开场白、计划、题目与插图 |
| `FileUploader.vue` | 最多 3 个文件并发上传，入队时固定可见性，维护逐文件状态及重试 |
| `AiConnection.vue`、`ContextMeter.vue` | 用户触发的模型连接检查及 64K 容量提示 |
| `DiagramEditor.vue` | 当前由 `TaskContent` 以只读方式展示结构图，无图片导出入口 |
| `BrandLogo.vue` | 提供的浅色 logo 与深绿色底色 |
| `RichText.vue` | Markdown 渲染与 HTML 清理，不接入 AI 生图 |
| `src/locales/en.json`、`zh-CN.json` | 双语界面文案；教学内容和模型回答保持原语言 |

教师模拟直接挂载 `StudentTask`，不维护第二套模拟交互。模拟使用专用草稿快照，真实学生使用发布版本。保存、应用生成结果或恢复版本后，编辑器重新挂载预览，避免沿用旧任务内容和模拟状态；模拟页面的作答状态不覆盖外层编辑器的未保存状态。

任务先保存再生成，生成结果通过修订号检查后应用，教师确认后发布。讲义通过补充提示词要求 AI 生成或修订，当前任务编辑页不提供手工讲义编辑或教师导出入口。学生材料与学习记录绑定明确发布版本；复制资源不携带学生记录。

只有真实学生可以将自己的学习结果导出为 Markdown，导出前先保存未保存的作答；教师、管理员及教师模拟不提供导出。导出内容排除参考答案、评价标准、教师私有材料和待审核的 AI 反馈。

历史前端阶段脚本源码保存在 `app/legacy/frontend/tools/`，验证产物已移入指定垃圾桶。`app/frontend/tests/brand-assets.mjs` 是 `build:brand` 使用的图标生成工具，保留原位。正式静态资源保存在 `public/`；`node_modules/` 和 `dist/` 由安装、构建命令重新生成，不随源码保留。

开发启动、AI 配置来源、关闭流程、已知限制及按日期记录的验证范围统一见[根目录 README](../../README.md)。按用户要求不新增测试类或测试脚本；运行与界面验证以当次授权为准。检查完成后关闭本次启动的服务并核验端口释放，仅在用户明确要求保留运行时例外。
