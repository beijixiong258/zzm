# 前端开发说明

当前前端使用 **Vue 3 + TypeScript + Vite**，共用中英文组件和语言资源；默认界面语言由分支配置决定，见[双语维护说明](bilingual-maintenance.md)。课件、题目、答案和教学语言仍使用各自保存的内容。应用版本保持 0.1.0。

## 本机开发

在 app 目录先运行 `pwsh.exe -File .\start.ps1 -NoBrowser` 启动后端；在 frontend 目录运行：

```powershell
npm ci --include=dev
npm run dev
```

开发服务器地址取自 `app/config.json` 的 `frontend` 节点，API 代理地址取自 `server` 节点。默认分别为 `http://127.0.0.1:18774` 与 `http://127.0.0.1:18773`。配置内容不注入浏览器，密钥只供后端使用。

```powershell
npm test
npm run build
```

构建先执行 Vue 模板和 TypeScript 类型检查，再生成 `dist/`。本机启动脚本由后端直接提供构建后的页面。修改源码后需要重新构建并刷新页面；也可以使用上述 Vite 开发服务器。

## 文件职责

以下路径均相对于 `app/frontend/`。

- `src/main.ts`、`src/vue/App.vue`：Vue 入口、登录状态、角色导航和页面加载。
- `src/vue/views/`：课程、教学设置、学习、版本、人员、材料库、设置和历史页面。
- `src/vue/components/`：公共页面标题、横向列表行、编辑窗口、通知，以及题目管理、材料管理、文档预览、导入组件。
- `src/vue/state.ts`：当前账号与课程、页面切换、未保存内容保护、站内确认。
- `src/vue/app.css`、`src/design-tokens.css`：公共样式、桌面和窄屏布局。
- `src/api.ts`、`types.ts`、`account-management-api.ts`、`document-api.ts`：沿用后端 HTTP 契约与类型。
- `src/study.ts`、`drafts.ts`、`stage2.ts`、`teaching-profile.ts`：作答规则、按账号和版本隔离的本地草稿、版本与教学规则。
- `src/material-upload.ts`、`document-state.ts`：真实上传进度、来源权限及文档修改回读。

题目管理先展示列表，通过同一个窗口新增或修改。修改、删除直接位于每一行。保存草稿和发布课程为两个独立动作。材料入库后可以关联多个课次；从课次移除材料只解除关联。

## 验证范围

现有接口、作答规则、文档客户端测试继续使用；旧 React 渲染测试及其专属页面已移出工作目录。Vue 题目组件交互测试覆盖新增、取消、修改、失败保留和删除确认。

`tests/vue-questions.test.ts` 使用内存 DOM 检查交互，不代表浏览器视觉验收。迁移阶段的四种视口尺寸、三种演示身份及交互记录见 [Vue 视觉检查记录](../frontend-vue-review-20261016/report.html)，双语页面及验证范围见[双语检查记录](../bilingual-review-20261016/report.html)。各记录只说明其标注轮次的实际检查结果。
