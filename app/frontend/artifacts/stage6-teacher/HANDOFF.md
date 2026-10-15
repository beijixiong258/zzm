# Stage6 教师工作台交接

## 可合并结果

- 教师页面默认左侧配置、右侧私有草稿试聊；窄屏堆叠并提供配置/试聊回跳。打开或重新打开不保存、不重置、不调用模型；只有明确 Start / Resume 才进入测试。
- 显示 unsaved banner、preview ID、已测试/当前保存 revision。试聊只用保存草稿；保存改动后旧对话仍可读，但 stale 时禁止继续发送，须明确 Reset my preview。已有工作或未发送文本时使用原生确认 dialog，可取消或先下载当前测试记录；pending 时禁用 reset 和教师 Save。
- 复用 `TutorMessage`、`QuestionPrompt`、`composerEnterAction`、`conversationScope`、草稿及 pending/ack helpers；请求带 `preview_id`。失败保留原文及同一 request ID，仅相同 completed ID 才 ack；reset 后新 generation 不读取旧文本/重试。紧凑面板没有正式提交或教师确认操作。完整学习预览保留为次级入口，不自动保存本地修改。
- 来源审阅支持保存题目、phase 和可选未保存指令 overlay；问题/材料仍明确来自保存草稿。显示准确 snippet、真实材料 ID、私有当前 reference、材料角色/排除原因和提取覆盖；不声称全文读完。输入变化立即隐藏旧编译结果，迟到响应不覆盖当前输入。
- 指令导入使用父提供的真实 multipart wrapper。支持检查/编辑、Append / Replace、显式 Apply to unsaved draft；错误、取消、迟到提取保留编辑。合并文本含分隔符计入 30,000 字符，超限禁用 Apply，不截断；不会附件入库、自动保存或发布。仅 patch instructions，不重置其他 dirty 字段。
- 教师载入、保存、材料轮询及各入口加入必要的会话迟到响应保护；availability/material 更新保留其他未保存字段。

## 本子任务文件

修改：
- `frontend/src/TeacherSession.tsx`

新增生产组件/独立样式/小 helper：
- `frontend/src/TeacherPreviewPane.tsx`
- `frontend/src/TeachingSourceReview.tsx`
- `frontend/src/InstructionImport.tsx`
- `frontend/src/TeacherExtractionReport.tsx`
- `frontend/src/teacher-workbench.css`
- `frontend/src/teacher-workbench-import.ts`

新增验证/交接（均在 `frontend/artifacts/stage6-teacher/`）：
- `index.html`, `harness.tsx` — 明确标注 synthetic 的真实 React 入口
- `fixture-http.mjs` — 独立本地 HTTP DTO 夹具，非真实 backend
- `browser-check.mjs`, `teacher-workbench.test.ts`
- `browser-results.json`, `screenshots/`, `HANDOFF.md`

未修改 `TeachingFramework.tsx`、shared API/types/App/core helpers、既有 guided workspace/message、通用 CSS、品牌/V4 资产、backend、root docs 或真实数据。

## 冻结接口接入

直接使用父提供的：`previewInfo(sid)`、`resetPreview(sid, expected_revision)`、`sourceReview(sid, body)`、`instructionPreview(sid, file)`、`tutorStart(sid, request_id, undefined, preview_id)`、`TutorTurn.preview_id`、`Workspace.preview`。`TeacherSession.viewerId` 为 optional，父 App 已传入当前账号 ID；夹具为 `fixture-teacher`。使用父的 generation-aware `conversationScope` / `draftKey` / `pendingKey` / `sameTurn`，没有复制协议或修改共享文件。

## 已执行验证

在 `D:/HermesProjects/EDUC7703/app/frontend`：

```bash
./node_modules/.bin/tsc -p tsconfig.json --noEmit
./node_modules/.bin/vitest run artifacts/stage6-teacher/teacher-workbench.test.ts
node artifacts/stage6-teacher/browser-check.mjs
```

- 当前全前端 TypeScript 检查通过；独立单元测试 **8/8**。
- Vite 实际构建教师 React 夹具后，以安装的 Chrome 通过真实本地 HTTP 验证 **19/19** 场景；桌面 `1440×1000` 与手机 `390×844`。
- 包括实际键盘 Start/Enter/Shift+Enter/Tab/Escape；IME composition 事件配合实际 Enter（不发送）；失败重试同 ID/错误完成 ID 不 ack；pending 的 Save/Reset 锁；保存→stale→取消/确认 Reset→generation 隔离；准确来源/私有 reference/coverage；迟到 source/import/session/workspace；multipart、30,010 字符提取不截断、combined 30,000 限额、Append/Replace；其他 dirty 字段保留。
- **0** unexpected browser errors、**0** 外网请求尝试、无 publish/student/submit/settings 写入。预期 HTTP 503/422 错误由测试主动注入。
- `finally` 关闭 owned Chrome/HTTP 服务；端口拒绝连接验证通过；删除自有 scratch。最终 profile/cache/build 全在 Hermes scratch，未放进 Vite watch 树。

### 截图

`screenshots/desktop-workbench.png`、`desktop-started-preview.png`、`desktop-stale-preview.png`、`desktop-source-review.png`、`desktop-instruction-import.png`、`desktop-instruction-confirmation.png`、`mobile-editor.png`、`mobile-preview.png`、`mobile-instruction-confirmation.png`。截图为匿名合成数据；已实际查看桌面和手机关键布局。

## 边界 / 父会话后续验收

- 本结果是 **built React + labelled synthetic HTTP 的 UI 验收**，不是 SQLite/真实 backend/native DOCX/PDF 提取、授权隔离或模型教学质量证明。实际 backend+SQLite+真实提取及恢复后的实模试聊由父合并验收；本子任务没有生产/API/provider/model 调用，也没有维护状态硬编码。
- 没有执行/宣称整包 production `npm run build` 或上线交付；夹具真实 build 成功。Vite 提示夹具 chunk 超过默认 500 kB，不影响验证，未越权做包拆分。
- IME 的 OS 候选窗口未驱动：实际测试 composition 事件保护及物理 Enter。原生文件/日期控件的 OS 文案可能随系统语言显示，本应用文本为 English。
- 如教学流程需要完整 reading-path/saved-response/submission 检查，使用明确的 full learning preview 次级入口；紧凑面板不重复完整学生旅程，也不实现父拥有的教师过程概览。
- 无新增依赖，无待解决 shared DTO/API 签名缺口。
