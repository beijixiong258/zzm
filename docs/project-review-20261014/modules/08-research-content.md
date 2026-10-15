# 08 · 课程原件、研究资料与首次种子

## 作用

项目根保存朋友交来的课程网页存档、课堂记录和原始材料；research保存需求研究与来源提取；app/sample_data提供首次初始化的可运行课程种子。

它们分别对应原始证据、产品/课程研究和应用数据入口。教学线上状态存放在生产SQLite，重新生成catalog不会更新已有课程。

## 目录职责

| 目录/文件 | 内容与使用方式 |
|---|---|
| `Interface`、按课次/参与者归档的根目录 | 浏览器保存的原始页面及配套_files资源；整套保留 |
| `Course Materials - Session 2/4` | 原始DOCX/PDF/PPTX/ZIP课程材料 |
| `chat-extraction` | 需求交流的提取产物；保留用于核对需求来源 |
| `docs/requirements-review.md` | 初始已确认需求、研究建议和范围区分 |
| `docs/materials-index.md` | 资料入口与网页存档索引 |
| `research/research-context.md`、`source-manifest.json` | 需求来源与原始页面目录 |
| `research/course-analysis/` | 文件inventory、页号文本、题目映射、扫描OCR和图像 |
| `app/sample_data/catalog.json` | 首次课程/课次/题目种子；服务端读取 |
| `app/sample_data/authoring.json`、`provenance.json` | 教师待复核内容、原始答案、来源定位和转换说明 |
| `app/sample_data/materials/student/teacher` | 拷贝原件与派生教学摘录，按角色鉴权 |
| `app/sample_data/assets` | 三幅原始散点图；运行时按课程/edition鉴权 |

## 课程数据流

`课堂原件 → research来源/题目映射 → sample_data构建 → 新库首次seed → 教师编辑草稿 → 发布immutable edition → 学生workspace`。

样例包含Session4的22个题目单元；Session2有19个候选，选择Pong/Bray之一后为14题。正式AI反馈、学生提交和教师确认是独立状态。

## 本轮核验

基础validator实际通过：41个唯一ID、41个DOCX题干核对、20个MCQ选项核对、3幅原图字节核对、10份原件副本、13份种子材料。参考记录分为28条原文来源和13条明确标记的review draft。

当前aicademiya后端在全新隔离库中实际导入2个session、41题、41参考、13材料；全部路径存在，用户/消息数量为0。证据：`evidence/catalog-validation.log`、`isolated-app-seed-backup.json`。

Session2 Part I的9条参考是待教师审核的派生指导；四条阅读澄清有来源核对和review标记。教师认可状态由审核/发布流程决定。

## 整理与边界

- 原始浏览器存档含课堂身份与学习记录，作为私有研究资料保存；公开代码仓库使用合成QA数据。
- 网页旁的_files是原页面组成部分，不能拆散清理。
- 研究question-map/provenance包含私有参考，留在服务端和内部资料入口。
- 原件中已发现的重复指南作为来源事实保留。实验副本和依赖下载另行分类，减少活跃目录体积。
- `sample_data/README.md`的旧品牌、公开题图说法和旧backend验证入口需要以当前说明替代；本轮保留来源详表并加当前入口提示。

本模块源码/原件均保留。实验模型和下载的回收清单集中在上层cleanup报告。
