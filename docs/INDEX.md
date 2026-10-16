# 项目文档

根目录 `README.md` 只保留项目名称。应用源码、配置和启动脚本位于 `app/`；本文索引使用说明、检查记录与历史材料。

## 使用与维护

| 文档 | 内容 |
|---|---|
| [本机运行](guides/local-setup.html) | Windows 启动、配置文件和硅基流动接入 |
| [前端开发](guides/frontend-development.md) | Vue 组件职责、开发入口和已有验证记录 |
| [双语维护](guides/bilingual-maintenance.md) | 中英文默认语言、分支同步和上传留言 |
| [项目协作约定](../app/AGENTS.md) | 修改范围、数据保护与协作规则 |

## 检查记录

| 记录 | 范围 |
|---|---|
| [双语检查](bilingual-review-20261016/report.html) | 中英文页面、语言切换及相关配置验证 |
| [Session 4 验收](session4-acceptance-20261016/) | 课程资料与教学流程记录 |
| [Vue 视觉检查](frontend-vue-review-20261016/report.html) | Vue 改造后的界面与交互 |
| [原前端审查](frontend-visual-review-20261015/report.html) | 改造前的界面问题 |
| [原项目审阅](project-review-20261014/README.md) | 原系统结构、问题及证据 |

## 历史材料

`history/` 保存从原 `app/` 根目录移入的 Stage 契约、工作流程、部署与运行记录。它们记录当时的项目状态；本机当前操作以 `guides/` 为准。历史材料中的服务器地址、源码定位和旧路径不代表本轮已重新验证。

- [历史文档目录](history/DOCUMENTATION.md)
- [Stage16 部署记录](history/DEPLOYMENT_STAGE16_RESULT.md)
- [运行与恢复](history/RUNTIME_V2.md)、[备份恢复](history/BACKUP-RESTORE-V2.md)
- [旧打包清单](history/PACKAGE_MANIFEST.json)：保留原字节与版本，仅对应原审阅包，不是当前工作树的校验清单。

各检查记录的截图与原始证据继续保存在各自目录中；模块内部的技术说明保留在对应模块旁，避免与项目首页混用。
