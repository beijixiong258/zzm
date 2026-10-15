# 问题清单与处理顺序

## 优先处理：有复现或直接执行证据

| 优先级 | 问题 | 影响与建议 | 证据 |
|---|---|---|---|
| P1 | 旧Student enrollment保留期清理新Teacher试聊 | 升级并获同课staff后，到期purge_learning仍按user/course清掉空version的教师workspace/messages；区分学生已发布run与当前staff preview，并补角色转换回归 | retention-role-reproduction.json；roster.py:20–51 |
| P2 | PPT/XLS/XLSX处理状态入口遗漏 | 无document且非PDF预览时缺按钮；用当前format capability一致判定入口 | targeted-ui-observations.json；Materials.tsx:170 |
| P2 | 前后端字符计数不一致 | 前端UTF-16早拒绝emoji/扩展字符；统一codepoint计数，保留输入并展示超限 | targeted-ui-observations与backend-character-validation；teaching-profile.ts:64/179 |
| P2 | 教学保存回读比对不覆盖完整payload | 标题、题目、参考不在teachingPreviewKey中；回读比较本次实际保存字段或可信revision | targeted-ui-observations；teaching-profile.ts:182–203 |
| P2 | 默认npm test缺storage条件 | Node静态render的2条断言执行前失败；明确测试storage fixture，400条conditional通过证据已保留 | frontend-tests.xml与frontend-webstorage-r2.xml |
| P2 | 样例validator旧backend路径 | --backend分支失败；更新当前模块入口并保留只读来源验证 | validate_catalog.py:218；本轮当前seed验证通过 |

## 已确认的协议边界

- **课程Roster导入**：commit后删除staging，缺逐请求committed receipt GET；前端当前正确保留unknown状态并只读检查。后续按需求补回执，避免误把当前名单当原响应。
- **文件上传**：已ack的ID保留；连接丢失走failed并允许retry，暂无exact upload receipt。区分unknown与rejected，再决定补幂等上传/恢复。
- **学习tutor回执**：最后完成ID能恢复常规pending，多标签先后完成的旧unknown需要针对性fixture确认。

## 静态发现，待定向验证

| 优先级 | 待核实项 | 已知代码事实 | 下一步 |
|---|---|---|---|
| P2 | 本人姓名/头像/Feedback并发撤权 | 某些本人写入在依赖鉴权后没有最终事务live_actor复核 | 用writer屏障复现，再做最小一致性修正 |
| P2 | Link抓取持SQLite写锁 | 部分PATCH在BEGIN IMMEDIATE内抓公共站点 | 合成慢HTTP源测锁等待，落库前重查权限/来源 |
| P2 | 多SELECT预览一致性 | 部分source-review/version preview无显式统一读事务 | 并发保存/发布时确认是否组合不同快照 |
| P3 | session trash marker跨edition restore | restore操作in_draft，不处理旧session_trash meta | 明确产品语义并补组合用例 |
| P3 | Session编号DTO边界 | Create ge1，Patch额外le9999 | 统一边界或明确兼容策略 |

## 已整理的项目入口

根README、app README/AGENTS、BUILD_CHECKPOINT、CONTRACT、DEPLOYMENT和sample_data说明已纠偏；Stage15/16最新路径混写已处理。历史原文保存在entry-documents-before.zip，历史文件继续原位可查。

## 后续维护建议

1. 建立私有Git代码基线，排除课堂原件、DB、配置、密钥与实验产物。
2. 大组件按实际功能修改时渐进拆分，保持各类receipt/draft作用域的差异。
3. 公网HTTPS与反代信任边界作为专门上线任务；当前内网HTTP仍适用于现有访问方式。
4. 保留真实教学质量样例与失败证据，特别是参考披露和复杂图表；它们属于质量评估，不能从unit测试通过推出全部正确。

本轮完成报告和清理，应用缺陷保留原实现供后续修复。优先级针对影响与当前证据，已复现、协议事实、待核验和维护建议分开列出。
