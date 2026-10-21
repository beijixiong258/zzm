# 双语分支维护说明

`vue-java-cys` 用于英文交付，`vue-java-cys-chinese` 用于中文展示。两边共用 Vue 组件、业务逻辑和 `app/frontend/src/locales/en.json`、`zh-CN.json`。两个分支只在 `app/config.defaults.json` 中的 `frontend.locale` 默认值不同：英文为 `en`，中文为 `zh-CN`。

`app/config.defaults.json` 提供可提交的默认配置；个人设置和密钥仍集中在不进入 Git 的 `app/config.json` 中，后者优先。个人配置不填写 `frontend.locale` 时，部署默认语言随分支切换；显式填写则固定部署默认语言。浏览器中已保存的界面语言偏好优先于部署默认值。切换分支后重启本机服务并刷新页面，无需为语言切换重复构建，两个分支使用同一份前端产物。

登录页和页面顶栏可以切换界面语言，浏览器会保存选择，刷新或重新登录后继续使用；未保存偏好时使用部署默认语言。本地存储不可用时，语言选择仅在当前页面内有效。界面语言只影响操作文字、日期和已知系统提示。课程原文、题目、答案、资料及 AI 教学语言仍按原内容和教学设置处理。第三方或尚未收录的错误原文会保留。

后续功能修改先在英文分支完成，同时更新两种语言资源；获得提交与上传授权后，再将英文分支合并到中文分支，保留中文默认值。不要将中文默认值合并到英文交付分支。

本项目按用户授权采用时间留言：新增提交及必要的合并提交均只填写实际提交时的北京时间，格式为 `YYYY-MM-DD HH:mm:ss`。上传前核对两条目标分支、实际留言和提交内容，不追加文字或正文，不重写既有历史。

在仓库根目录核对：

```powershell
git diff vue-java-cys vue-java-cys-chinese --name-only
git diff vue-java-cys vue-java-cys-chinese -- app/config.defaults.json
```

正常应只显示 `app/config.defaults.json` 中一行默认语言差异。源码、运行配置、启动脚本和数据目录均继续位于 `app/`；文档移动不改变运行路径。

本机配置见[本机运行说明](local-setup.html)，前端开发见[前端开发说明](frontend-development.md)，实际双语视觉检查见[检查记录](../bilingual-review-20261016/report.html)。
