# AIcademiya · 代码审阅包

本包包含当前后端/前端源码、测试与合成fixtures、构建配置、工具/运行模板、预构建前端及八份模块报告。生产基线是Stage16 R4/API0.11/schema9。

## 阅读入口

1. `docs/project-review-20261014/README.md`：项目结构与模块索引。
2. `docs/project-review-20261014/issues.md`：已复现与待核实的问题。
3. `docs/project-review-20261014/verification.md`：本机实测、环境条件和范围。
4. `app/backend/aicademiya`、`app/frontend/src`：当前源码。

## 安装与本地检查

依赖目录没有打包。使用独立Python环境安装 `app/backend/requirements.txt`；从app/frontend运行 `npm ci`，然后 `npm test`及 `npm run build`。Windows项目使用Python3.13；当前测试在Node26上需要明确Web Storage环境，见verification。

后端常规测试使用 `backend/tests/conftest.py` 自建合成课程与独立临时DB。可先从app运行：

`python tools/run_backend_tests.py backend/tests -q --ignore=backend/tests/test_v2_release.py`

`test_v2_release.py`依赖被排除的真实private_seed来做完整发布包验证，本包保留其源码供审阅。其它特定浏览器/远程/旧stage工具可能需要原验收资源或本机路径。

本包不含实际课程seed和生产用户数据；普通应用启动可检查空站点，不会出现原课堂课程。若要复现真实课程教学，另行接收课程材料并配置模型。模型、Tavily、GPU工作器及远端部署不是代码审阅的自动步骤。

## 包含与排除

包含：当前运行源码、完整后端/前端测试源码、合成扫描/Office fixtures、必要品牌测试baseline、前端静态资源、依赖锁文件/版本约束、部署和备份代码、现状报告。

排除：.venv/node_modules、模型、DB/WAL/SHM、uploads、local-settings及实际.env、SSH身份、真实课堂网页/身份/学习记录、private sample_data、原始研究语料、历轮大产物/下载/浏览器profile和大批测试日志。

源码/文档仍含本机与内网部署路径供定位。本包用于朋友间私下审阅；公开Git发布前需要独立处理版权、课程材料与运维定位信息。

## 校验

`PACKAGE_MANIFEST.json`给出每个文件字节数与SHA256。ZIP的SHA256及大小另存外部package-summary.json。只读打包未修改源项目，尚未上传到微信、网盘或GitHub。
