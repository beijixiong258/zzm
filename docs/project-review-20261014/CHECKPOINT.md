# 整理完成交接

用户目标：整理AIcademiya现状、各模块报告和冗余清理；本轮不限时，确认可重建下载免另备份回收。

## 完成状态

- 八份模块报告、总览、issues、verification、cleanup与源码映射齐全；187个相对链接验证通过。
- 55后端/93前端/31当前runtime工具文件映射到模块；覆盖清单区分全文与选段/结构读取。
- 回收13目标/28,694文件/7,791,029,093字节；全$I/$R及payload字节核验，原生Restore小样通过。
- 7份入口文档备份并纠偏；历史记录/源码/课堂原件/数据库/配置保留。
- 后端1364通过/1skip，后台proc_1ce355cb4041已exit0；前端默认398+2环境失败、明确Web Storage400通过；独立build通过。
- 远端R4/API0.11/schema9，134发布文件/27HTTP匹配；132直接本地匹配+2builder转换已解释，清理后再核134输入无改动。
- 实际生产匿名桌面/手机通过；fresh current seed/14文件backup restore通过；没有生产写入/服务重启/模型搜索调用。

## 已复现问题

1. 旧Student enrollment保留期会删除随后获同课staff的Teacher preview工作区/消息。
2. 无document/non-PDF preview时PPT/XLS/XLSX缺处理状态入口。
3. UTF-16字符限制600emoji计1200，后端接受600codepoints。
4. 教学保存回读key不覆盖title/questions/reference_answers，纯helper已确认范围。

应用实现保持原状，后续修复按issues.md优先级执行。不要重跑回收/Stage16切站。两路子任务已交回，无待执行后台工作。本轮最终入口README.md。
