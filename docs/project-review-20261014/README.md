# AIcademiya · 当前情况与模块报告

## 结论

**项目已经形成可运行的教学平台。当前整理重点是入口和依赖分层。** 本地代码、课堂原件、历轮试验和部署证据混在同一项目树，旧README/AGENTS把读者带回早期阶段。服务器当前运行Stage16 R4，源码主链和线上发布字节相符。

本轮完成范围：结构库存与开发会话读取、八模块审阅、隔离复测、远端只读回读、入口文档纠偏和可恢复清理。具体结果从 [验证记录](verification.md)、[问题清单](issues.md)、[源码职责图](source-map.md)与 [清理记录](cleanup.md)进入。

## 当前运行状态

| 项 | 状态/路径 |
|---|---|
| 生产网站 | http://192.168.32.55:18773/，PVE CT255 |
| 版本 | AIcademiya_V2-stage16-workflow-r4；API0.11.0 / schema9 |
| 代码主栈 | FastAPI + SQLite + React19/TypeScript/Vite |
| 线上数据 | /var/lib/aicademiya/aicademiya.sqlite3 与uploads |
| 线上账号/课程/材料 | 43 / 4 / 26 |
| 线上学习记录 | 21条消息、2条作答、4条revision |
| 文档任务 | 9完成、4失败；当前无queued/running |
| 教学端点健康 | 文本容量3，视觉容量1，队列0 |
| 注册与演示 | 注册关闭、demo关闭 |
| 访问入口 | 当前内网HTTP；公网HTTPS入口留待独立上线工作 |
| Windows启动 | app/start.cmd；正常本机数据默认app/data-v2 |
| 源码版本历史 | 本地项目和app均未建立Git仓库 |

观察时间和完整字段见 `evidence/remote-production-readback.json`。读取了朋友开发会话 `20261014_012234_f3f4f4` 的原始首尾与最终发布记录，并用源码/服务器回读校验其Stage16结论。

## 整体数据流

```text
课堂原件 / research来源
    └─ 首次课程种子 → 新库初始化
教师 → 课程草稿 → 文件/Worksheet与教学配置 → 发布edition
学生 → 已发布workspace → 对话/修订 → 显式提交 → 教师确认/退修
                      └─ Tutor → CT socket proxy → GPU router
材料上传 → shared Material → Session关联 → 文档job
                                  └─ 受限SSH工作器 → 原生/图文bundle → immutable revision
SQLite + uploads + 历史引用 → 精确绑定备份 → 新目录恢复
```

课程edition固定学生看到的课程内容；文档revision固定原文件的处理结果；教师preview是本人草稿试聊。三个标识分别解决课程发布、来源更新和试聊隔离。

## 八个模块

| 报告 | 解决的问题 |
|---|---|
| [01 账号、权限与安全](modules/01-accounts-security.md) | 谁能登录、管理账号和访问课程；请求/文件安全 |
| [02 课程、教学编排与版本](modules/02-course-authoring-versions.md) | 草稿/发布、staff、教学设置、预览和生命周期 |
| [03 学习与教学对话](modules/03-learning-tutor.md) | 引导式学习、作答/追问、请求恢复、参考和提交 |
| [04 前端与状态](modules/04-frontend-experience.md) | 页面/组件入口、跨刷新草稿、navigation和界面依赖 |
| [05 材料与完整文档](modules/05-materials-documents.md) | 文件复用、CPU/GPU处理、来源校订和Worksheet |
| [06 AI与搜索服务](modules/06-ai-search-services.md) | provider、模型请求、搜索、scope和连接检查 |
| [07 部署、数据与工具](modules/07-deployment-data-tools.md) | 本机/线上入口、发布allowlist、备份和验证 |
| [08 研究与课程来源](modules/08-research-content.md) | 课堂原件、题目来源、种子和教师审核 |

## 项目为何显得乱

1. **现行入口与历史记录混写。** 根README停留2026-10-03，AGENTS仍指Stage2，appREADME同时列Stage15/16。入口已纠偏，历史文档由DOCUMENTATION索引保留。
2. **实验下载与运行依赖混放。** 旧模型、未完成下载、Linux wheels和实验venv占据大量目录。确认可重建部分已回收，保留结果与恢复来源。
3. **Stage目录名不等于过期。** 当前文档工作器继续复用Stage12/13/15代码，发布allowlist才是运行依赖依据。
4. **重复组件和迁移文件有兼容职责。** 模块报告通过导入/路由和版本分支确认用途，避免按名字清理源码。
5. **本地缺Git基线。** 当前部署有字节manifest，源树开发历史主要留在会话/Stage记录。后续建立私有代码仓库更利于回退和追踪。

## 本轮发现与后续优先顺序

后端1364通过/1跳过；前端明确Node Web Storage环境400通过，默认环境398通过/2失败；构建通过。已在隔离数据复现旧Student保留期清理新Teacher试聊，另确认新增格式状态入口、字符计数与保存回读范围问题，见issues。

- **当前即可使用：** 本轮报告入口、当前Stage16使用流程与现存内网网站。
- **开发整理：** 明确frontend测试storage fixture，修复旧seed validator的backend路径；保留默认失败和修复条件的证据。
- **版本管理：** 在独立授权中建立私有代码Git基线，课堂原件、密钥、DB与实验产物分开排除。
- **发布：** 公网HTTPS/反代边界以及真实教学质量测试按专门上线任务执行。

本轮应用功能、生产账号/数据与远端服务保持原状。检查的证据层次和保留项集中记录于verification/cleanup。
