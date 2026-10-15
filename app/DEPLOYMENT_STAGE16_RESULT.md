# AIcademiya Stage16 部署结果

## 结论

**Stage16 已部署并完成生产回读。**

- 网站：http://192.168.32.55:18773/
- 切换完成：2026-10-14 10:31:31（UTC+08:00）
- 当前应用：`/opt/aicademiya/releases/AIcademiya_V2-stage16-workflow-r4`
- 当前指针：`/opt/aicademiya/current`
- 应用 API 0.11.0，数据库 schema 9。
- 文档工作器：`/opt/aicademiya-documents/releases/stage16-materials-r1`，21个服务器运行文件，root拥有且不可由工作器用户改写。
- 最后查询周用量10%，未触及本轮12%停工线。

## 六项交付

| 请求 | 已实现及验证 |
|---|---|
| Session编辑/删除 | Home卡片可编辑编号、标题、描述；明确删除确认和Deleted sessions恢复入口。删除是从当前草稿可恢复移除，保留同ID、历史发布版、学习记录及共享文件；学生发布版变化仍需明确发布。 |
| Materials工作流 | 文件夹选择、相对路径/选中文件列表、文件大小、真实XHR字节进度、逐文件type/可见性、已上传type编辑、直接Remove入口。按实际成功文件区分preview/full/mixed提示，失败文件不被算作成功。移除Session关联不删除课程共享原件。 |
| DOC/PPT/XLS/XLSX | DOC既有路径保留；旧PPT/XLS真实LibreOffice转换及XLSX全sheet/stored-cell读取接线完成。实际CPU与已安装UID999工作器/应用入口均通过。 |
| AI连接状态 | 共享30秒轻量检查、检查时间/失效状态、配置变更绑定、不可达/恢复及登出清理。轻量reachability/capacity与手动Generation check分开，前者不冒充生成质量证明。 |
| Worksheet识别/答案匹配 | 默认AI检测，识别题目、选项、空格及组别，可选现有私有Answer key；只接收来源支持的答案，缺失或不受来源支持者留空，老师审核编辑后保存。 |
| 从Materials复用Worksheet | Questions & answers使用“Select worksheet from the materials”，不再要求二次上传；沿用原Material ID/原文件，验证来源/版本未改变，审核提交保留来源谱系，不自动发布。 |

## 实际验收

### 本地与浏览器

- 最终后端：**1364 passed，1项既有skip**。另有既有Starlette弃用提示，不是测试失败。
- 前端：**400 passed**，生产构建通过。
- 真浏览器工作流：4组、**23项检查通过**。实际目录输入、XHR进度、类型修改、直接移除、Session编辑/删除/恢复、Worksheet复用/审核/提交、AI轮询/实际socket断连恢复/过期/登出停止均有回读。
- 8个桌面/手机布局状态通过边界检查；另对实际截图进行了目视检查。
- 窗口隐藏/恢复的事件分支已验证，但Windows自动化浏览器的原生OS visibility未验证，相关测试明确使用了live DOM事件模拟。

### 真实模型与格式处理

- 3次实际候选CT应用→教学router→V100调用，均HTTP200、finish=stop：
  - 分组重复编号的Worksheet与独立key：4题，选项和空格保留，3条提供答案正确对应，缺失项无答案。
  - 内联答案：数学符号`x² ≥ 16`及所供答案保留。
  - 无key：2题的模型原始`reference_answers`为空，不是仅靠后置过滤才留空。
- 私有marker答案没有进入公开题干/hint；审核保存后的原件字节与Material ID保持不变。
- DOC/PPT/XLS/XLSX各native/prepared，共**8个真实合成文件CPU路径通过**，不是伪造转换器结果。
- 实际安装应用→受限SSH→UID999工作器的4格式上传处理通过：
  - XLS、XLSX：原生处理，无GPU lease，各保留1条teacher-only评论。
  - DOC：2页，使用独占GPU，实际1次选中页模型调用，完整转录回执通过。
  - PPT：2页，实际2次页模型调用，两条真实讲者备注正确保留。
- 处理完成后教学容量恢复3路、vision1、队列0。V100/T10-A保持原PID；T10-B仅按既有文档独占租约正常停止/恢复。

这些是已列明合成样例和实际运行链路的证据，不代表任意Worksheet、历史课堂语料或所有图表关系达到100%理解准确率。机器提取仍需老师审核。

## 本轮现场问题及修复

1. preview-only上传错误宣称完整处理正在后台进行：已按成功上传文件的真实模式生成提示，并覆盖mixed/部分失败情况。
2. LibreOffice未安装Calc，真实XLS导出虽返回0却无输出：经用户在独立sudo终端授权补装同版本Calc及依赖，新增5包，现有包版本不变。
3. 旧PPT转换丢失`p:ph`页码标志，留下field-only `a:fld type=slidenum`：按结构排除自动页码，不按文本删除，不损坏真实备注或作者写入的`<number>`。
4. 应用队列提交仍使用旧格式备注白名单：加入PPT/XLS/XLSX，使用实际queue/API提交回归及重新安装应用链路验收，未绕过评论检查。

所有失败产物和原始文件均保留。早期候选R3及失败QA记录不作为最终部署成功证据。

## 数据与运行时保留

- 切换前暂停网站并做最终一致备份：`/var/backups/aicademiya-stage16-r4-cutover`。
- 恢复演练：`/var/backups/aicademiya-stage16-r4-rehearsal` → `/var/lib/aicademiya-qa/stage16-release-r4/restore-rehearsal`。
- 演练核验**4970个文件**，records_match/files_match均为true。
- 最终切换逐个校验**27张表的既有命名列记录**，全部保留。关键前后数量相同：43用户、4课程、26材料、21消息、2作答、13文档任务、9文档revision。
- 既有4个失败文档任务未自动重试；旧资料未静默重新提取、重新发布或改写历史版本。
- 独立同ABI Python3.13.5 venv，51个包版本保持不变，pip check通过。
- 正式网站实际进程环境已启用新格式；demo关闭。
- 134个发布文件逐字节核验，27个公开资源经HTTP核对。
- 使用**生产实际worker argv和UID999**做了独立XLSX原生命令检查；不写生产DB、不用GPU，结果通过。
- 生产桌面/手机匿名页面通过，无登录尝试、无数据修改；所有测试浏览器和QA服务已关闭，18776端口关闭，临时grace override已退役。
- 网站切换前后3个GPU进程PID一致；未重启教学模型或router。
- 旧网站版本及原数据/历史资源仍保留，不执行额外清理。

## 使用边界

- Session删除和Materials移除不是物理擦除历史数据/共享文件。
- 100%上传只代表字节发送完成，文档处理状态另行显示。
- Excel预览是**原生单元格账本与原始媒体**，不是Excel打印布局。XLSX公式原文与缓存值分离，不求值、不刷新；旧XLS经LibreOffice转换的缓存/值明确标记为转换所得，不宣称直接解码了原始二进制缓存。
- AI连接指示不等于生成质量保证。格式/图像/答案关联不明确时仍应审核。

## 关键证据

项目根：`D:/HermesProjects/EDUC7703/app`

- `artifacts/stage16/backend-all-r4.xml`
- `artifacts/stage16/frontend-all-r3.xml`
- `artifacts/stage16/browser/20261013T180954Z-aa1e2c/`
- `artifacts/stage16/live-worksheet/20261013T183016Z-31b12c/`
- `artifacts/stage16/legacy-real/20261013T185410Z-bb5cb6e1/`
- `artifacts/stage16/worker-install-readback.json`
- `artifacts/stage16/installed-worker-app-r2/`
- `artifacts/stage16/site-stage-r4.json`
- `artifacts/stage16/site-rehearsal-r4.json`
- `artifacts/stage16/cutover-result-r4.json`
- `artifacts/stage16/postdeploy-result-r4.json`
- `artifacts/stage16/precutover-gpu.json` / `postcutover-gpu.json`
- `artifacts/stage16/production-browser-r4/`
- `artifacts/stage16/final-live-state-r4.json`
