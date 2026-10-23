# 前端开发

Vue 3 + TypeScript + Vite，应用版本沿用 0.1.0。开发服务器默认 5173，浏览器直接请求 8001 的业务接口；通过 `VITE_API_BASE_URL` 可指定完整 API 地址。

| 入口 | 职责 |
| --- | --- |
| `app/frontend/src/vue/ClassroomApp.vue` | 登录方式、语言、课程导航及角色页面 |
| `classroom-state.ts` | 账号、课程、导航和未保存修改保护 |
| `app/frontend/src/classroom-api.ts` | 类型契约、HTTP 调用、下载及学生内容投影 |
| `ClassroomHome.vue`、`CoursePeople.vue` | 三项课程设置、班级成员及个人邀请码 |
| `TeacherWorkbench.vue` | 独立教师工具入口及保存资源 |
| `TaskEditor.vue` | 材料多选、生成、讲义编辑、复制、导出及学生模拟容器 |
| `StudentTask.vue` | 学生页面及教师模拟共用，包含阅读、作答、附件、对话、提交与历史 |
| `TaskMonitor.vue` | 学生进度、作答与对话审阅、AI 反馈审核 |
| `TaskContent.vue` | 学生可见讲义、开场白、计划、题目与插图 |
| `FileUploader.vue` | 最多 3 个文件并发上传，入队时固定可见性，维护逐文件状态及重试 |
| `AiConnection.vue`、`ContextMeter.vue` | 用户触发的模型连接检查及 64K 容量提示 |
| `DiagramEditor.vue` | 可编辑节点、连线、布局及 SVG／PNG 导出 |
| `BrandLogo.vue` | 提供的浅色 logo 与深绿色底色 |
| `RichText.vue` | Markdown 渲染与 HTML 清理，不接入 AI 生图 |
| `src/locales/en.json`、`zh-CN.json` | 双语界面文案；教学内容和模型回答保持原语言 |

教师模拟直接挂载 `StudentTask`，不维护第二套模拟交互。模拟使用专用草稿快照，真实学生使用发布版本。保存提示词后由教师刷新或重开模拟；模拟页面的作答状态不覆盖外层编辑器的未保存状态。

任务先保存再生成，生成结果通过修订号检查后应用，教师确认后发布。学生材料与学习记录绑定明确发布版本；复制资源不携带学生记录。任务文档仅导出 Markdown，学生版排除参考答案、评价标准和教师私有材料。

历史前端阶段脚本与验证产物分别归入 `app/legacy/frontend/tools/` 和 `app/legacy/frontend/artifacts/`。当前 `build:brand` 使用的 `app/frontend/tests/brand-assets.mjs` 保留原位；前端入口、依赖、静态资源和构建目录路径保持不变。

开发启动、环境变量、已知限制及验证记录统一见[根目录 README](../../README.md)。2026-10-23 的功能修复已完成前端类型检查和相关接口、浏览器验证；随后进行的目录整理仅核对文件清单、路径引用和前后端运行状态，没有重新编译或执行全量测试。
