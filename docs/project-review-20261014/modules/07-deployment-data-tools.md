# 07 · 启动、发布、部署、数据与验证工具

## 当前运行结构

| 层 | 当前入口 |
|---|---|
| Windows开发源码 | `app/backend/aicademiya`、`app/frontend/src` |
| Windows启动 | `app/start.cmd → .venv/Scripts/python.exe tools/launch.py` |
| 本机数据默认 | `app/data-v2/aicademiya.sqlite3`；本轮前尚未创建 |
| 旧本机数据 | `app/data/`；保留且与V2分开 |
| 生产网站 | PVE CT255，`http://192.168.32.55:18773/` |
| 生产release | `/opt/aicademiya/current → releases/AIcademiya_V2-stage16-workflow-r4` |
| 生产数据 | `/var/lib/aicademiya/aicademiya.sqlite3` 和 `uploads/` |
| 服务与配置 | `aicademiya.service`；`/etc/aicademiya/aicademiya.conf` |
| 远端文档工作器 | Stage16文档release、UID999受限SSH链路 |

网站绑定192.168.32.55而非127.0.0.1，loopback模型proxy绑定18280。远端核验可从私有IP访问网站。

## 构建与发布

`frontend/package.json`使用React19、TypeScript、Vite和Vitest。正式后端通过预构建frontend/dist提供单站点入口。

`tools/build_v2_release.py:21–159`采用显式allowlist：55个后端模块、受控frontend chunks、运行脚本及Stage12/13/15/16解析代码。发布代码包和private_seed分开；DB、配置凭据、venv、node_modules、测试数据不进入代码包。

两项构建转换已逐字节验证：发布的 `tools/start-linux.sh`取自 `runtime_v2/start-linux.sh`；warmer默认数据目录从data替换成data-v2。除这两项外，132个本地运行文件直接匹配远端。完整134个发布文件均匹配远端manifest，27个HTTP资源匹配发布字节。

`tools/teaching_stage16/site_release.py`是固定Stage16 cutover工具，包含旧release断言、备份/回滚及systemd变更。它作为历史发布证据保留，未来升级要为新的旧/新版本制定入口。

## 数据与备份

SQLite存账号、课程、immutable edition、作答/消息、staff关联、材料、导入预览、文档任务/revision等。生产有27个业务表。数据库integrity=ok，foreign_key_check为空。

`tools/backup_data.py`通过SQLite backup API生成一致副本，并收集当前Material、历史snapshot和pending import的精确资源绑定。restore写新目录，重定位绑定并验证records/files/schema。代码/前端、私有配置、SSH身份和GPU权重另行保存。

本轮以全新隔离种子库执行启动与14文件backup/restore，records_match/files_match均为true。生产采用只读检查，43用户、4课程、26材料、21消息、2作答；有3课程trash记录，属于应用可恢复状态。

## 验证工具的分层

1. `tools/run_backend_tests.py`：当前pytest总入口，唯一retained scratch，避免用户数据。
2. `npm test`：当前前端单元测试；本机Node26需显式Web Storage环境，默认命令出现2项localStorage测试环境失败。
3. `run_stage*_integration/regression.py`：按形成阶段保留的组合工具，执行前先读版本/端口/AI adapter条件。
4. `run_remote_*`、`live_*`、`warm_*`、`site_release.py`：部分会启动QA、真实模型、安装或切站；通过名称之外的函数实现确定动作。
5. 本轮 `docs/project-review-20261014/tools/`：库存、只读服务器回读、匿名浏览器、隔离seed/restore与回收工具。

## 当前问题

- **P1：文档入口落后。** 旧根README、AGENTS、BUILD_CHECKPOINT会把读者带回Stage1/2/3。本轮更新入口并保留原文zip备份。
- **P1：本地缺少Git基线。** 项目根和app均不是Git仓库；发布manifest能验证部署字节，不能提供本地开发提交/分支历史。建议在后续授权中建立仅包含代码与合适文档的私有源码仓库。
- **P2：测试环境未显式固化。** 默认npm test本轮398通过/2失败；启用Node Web Storage及独立存储文件后400通过。建议测试setup提供明确storage fixture。
- **P2：旧样例验证入口残留。** `sample_data/validate_catalog.py --backend`仍访问 `backend/akademiya/db.py`；当前模块为aicademiya。基础来源验证通过，当前seed另用本轮隔离实测验证。
- **P2：候选提取树有不可读条目。** 首轮库存234个lstat错误集中在旧候选extract树，另有219个reparse条目跳过。它们保留原位，数量作为库存边界记录。

## 保留规则

保留app/.venv、frontend/node_modules/dist、local-settings文件、所有用户数据库/上传、private_seed、旧release来源与独有QA结果。生产当前13份原件引用20261006旧release，整个旧目录不能作为垃圾。

已回收7.79GB本地可重建下载/实验环境/研究浏览器profile。移入回收站缩小活跃项目；磁盘空间在用户清空回收站后释放。
