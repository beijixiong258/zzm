# 前端开发

Vue 3 + TypeScript + Vite，应用版本沿用 0.1.0。开发服务器为 5173，浏览器直接请求 8001 的业务接口；无开发代理。不同部署地址可通过 `VITE_API_BASE_URL` 指定完整 API 地址。

主要入口：

- `app/frontend/src/vue/ClassroomApp.vue`：登录、语言切换、课程导航和角色页面。
- `app/frontend/src/vue/classroom-state.ts`：账号、课程、导航及未保存修改保护。
- `app/frontend/src/classroom-api.ts`：驼峰字段契约、HTTP 调用和学生内容投影。
- `ClassroomHome.vue`、`TaskEditor.vue`、`StudentTask.vue`、`TaskMonitor.vue`：教师首页、任务编辑、学生学习和监控。
- `CourseLibrary.vue`、`CoursePeople.vue`：材料库与班级管理。
- `TaskContent.vue`：学生任务展示与教师右侧预览共用组件。预览不包含聊天输入。
- `TaskQuestionEditor.vue`、`MaterialTree.vue`：题目编辑和材料目录树。
- `src/locales/en.json`、`zh-CN.json`：双语操作文案；课程内容与 AI 输出保留实际教学语言。

在前端目录运行 `npm run dev`。按实际需要使用 `node node_modules/vue-tsc/bin/vue-tsc.js --noEmit` 检查类型；`npm run build` 生成部署产物。不新增测试类，不将静态检查结果表述为完整联调通过。

任务先保存草稿，再发起生成；生成结果通过版本检查后应用，教师确认后发布。学生材料与学习记录始终携带发布版本。旧的 Python 接口页面、辅助模块及对应测试已移出工作区；当前入口只有 `ClassroomApp.vue`。
