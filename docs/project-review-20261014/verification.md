# 本轮验证记录

## 执行结果

| 验证 | 本轮实际结果 | 证据 |
|---|---|---|
| 当前后端全量 | 1364通过、1跳过、0失败；559.97秒 | `evidence/backend-full-r2.xml` / `.log` |
| 前端默认npm test | 398通过、2失败；Node无localStorage | `evidence/frontend-tests.xml` / `.log` |
| 前端明确Web Storage环境 | 400通过、0失败 | `evidence/frontend-webstorage-r2.xml` / `.log` |
| TypeScript与生产构建 | 通过；输出到本报告evidence/frontend-build，现有dist保留 | `evidence/frontend-build.log` |
| 本机launcher prerequisites | ready；当前venv、frontend与catalog可用 | 实际 `tools/launch.py --check` 回执 |
| 种子来源校验 | 41题干、20选项、3题图、10原件副本通过 | `evidence/catalog-validation.log` |
| 当前seed/应用启动 | 2session、41题、41参考、13材料，全部路径解析；health/bootstrap200，匿名me401 | `evidence/isolated-app-seed-backup.json` |
| fresh seed备份恢复 | 14文件，integrity=ok，records_match/files_match=true | 同上 |
| 生产版本/文件 | R4/API0.11；134文件匹配manifest，27HTTP资源匹配 | `evidence/remote-production-readback.json` |
| 本地代码与发布 | 132直接字节匹配；2个builder定义转换匹配，无意外漂移 | `evidence/release-transform-check.json` |
| 生产SQLite | 27业务表，integrity=ok，FK错误0 | remote-production-readback |
| Router健康 | 文本容量3，视觉1，queue0 | `evidence/router-health-readback.json` |
| 线上匿名桌面/手机 | 实际浏览器通过；0pageerror、0写请求、浏览器关闭 | `evidence/production-browser/result.json`与截图 |
| 回收及恢复性 | 13目标/28,694文件全载荷校验；D盘原生Restore小样通过 | `evidence/cleanup-result.json` |

## 测试环境与执行记录

后端第一次前台运行到约79%后受工具420秒窗口中断，保留 `backend-tests.log`。第二次由后台进程 `proc_1ce355cb4041`完成，exit_code=0，XML逐case汇总1364通过+1跳过。跳过项为 `test_provided_student_worksheet_read_only`，要求显式opt-in；基础来源验证和当前seed另行执行。

前端运行Node26.7.0、Vitest3.2.7、Vite7.3.6。默认测试两项在React静态渲染中触发SavedResponses→readDraft默认参数 `localStorage`，先于测试的参考/隐私断言失败。使用当前Node提供的 `--webstorage`和独立 `--localstorage-file`后400项通过，源码与测试断言保持原样。建议将storage fixture纳入正式测试setup，让普通npm test也能重复通过。

TypeScript noEmit和Vite build通过；主index chunk约533kB，Vite给出500kB分块建议。实际产物是独立构建目录，当前应用dist未替换。

旧 `sample_data/validate_catalog.py --backend`仍指 `backend/akademiya/db.py`，本轮该入口实际失败。基础validator通过；当前 `backend.aicademiya.Database`在全新scratch库实际导入并通过应用/备份恢复验证。

第一次本轮isolated smoke使用了继承TMPDIR（系统Temp）。已将其自建fixture移到Hermes scratch，并以显式scratch新目录重跑；最终证据以 `isolated-app-seed-backup.json`为准，R1回执保留。后端runner本身使用明确Hermes scratch。

## 定向问题复现

### 跨角色保留期

在全新合成DB中使用当前角色变更、staff分配、session access和maintenance函数：已移出的Student升级Teacher、获同课staff、新建本人preview之后，原enrollment到期清理把workspace/messages从1/1删除到0/0，teacher_previews binding仍为1、staff关联仍有效。已复現业务层范围缺陷。

证据：`evidence/retention-role-reproduction.json`、`tools/retention_review.py`。本轮采用合成状态和实际业务函数，未操作生产账号。

### 前端条件与字段匹配

真实React组件静态渲染合成材料：无document/non-PDF preview时，9个原有格式显示处理状态入口，PPT/XLS/XLSX不显示。条件来自Materials.tsx:170。

实际纯helper验证：600个emoji在前端tone校验中计1200 UTF-16单位并拒绝；后端TeachingProfile接受600 codepoints。不同title/questions/reference_answers的输入在当前teachingPreviewKey中相同，证明保存回读比较范围不足；本轮未模拟生产写入丢失。

证据：`evidence/targeted-ui-observations.json`、`backend-character-validation.json`和 `tools/targeted_ui.tsx`。

## 核验范围

本轮CPU测试、合成DB/组件复现、当前代码包与远端只读状态、匿名桌面/手机均有实际回执。当前logged-in全教学浏览器流、真实生成/搜索质量和完整DOC/PPT/XLS/XLSX远程重处理沿用Stage16已列明历史证据；本轮没有新增这些调用。并发撤权/长Link写锁、多标签lost-ack等静态风险列于issues，等待针对性复现。

应用功能、生产数据/配置、模型/网站服务及当前运行依赖保持原状。既有Starlette/httpx弃用warning单独记录，未安装或升级依赖。
