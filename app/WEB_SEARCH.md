# AIcademiya · Tavily Web Search

本文对应Stage7源码/API0.6.0；实际部署以最新deployment result为准。

## 使用与网页配置

学生及教师自己的试聊可以选择本轮Web search，默认关闭。全局允许搜索只提供能力，不自动打开个人开关；教师观察学生记录不代替学生操作。

管理员进入 **Settings → Web Search**，设置Allow web search、替换API key、保存并显式Test search。留空保留当前key；Clear the current key on save明确清除，旧环境key不会重新启用。GET仅回已配置状态/来源，绝不回显key；key不写浏览器持久化或日志。

SQLite的web_search_enabled/web_search_api_key覆盖环境；无该记录时继承AICADEMIYA_WEB_SEARCH_ENABLED/TAVILY_API_KEY。保存即时生效并在重启后保留，不修改进程全局环境。CT255环境配置在/etc/aicademiya/aicademiya.conf，Windows本机文件为local-settings-v2.json；旧EDUC_*命名和local-settings.json不是当前V2配置。

全局配置由后端admin权限保护，教师/学生只能控制自己的逐轮搜索开关。密钥随私有数据库备份；缺失密钥/关闭服务会显示真实原因，不自动切换到模拟模式。

## 连接检查

Configured不等于连接成功。页面分别显示Not configured、Not checked、Last test succeeded或Connection issue及最近检查时间。检查绑定有效配置，修改后失效；并发A→B→A变更也拒绝过期结果。GET、打开页面和保存不自动调用服务。

Test search只用保存的配置发出一条固定公开主题查询，不发课堂内容；会消耗Tavily额度。它证明一次服务调用，不证明教学质量。正常产品无Feedback/Demo切换；显式开发QA adapter不用于生产兜底。

## 教学搜索调用链与边界

- 关闭：跳过查询规划与Tavily，直接辅导。
- 打开：通过标准tools/tool_calls/tool_choice强制模型给出web_search查询；NO_SEARCH或不合规响应显式报错，不假装查过。
- 规划只见公开题目/材料/本轮需求。Tavily仅接收短查询，不接收整份workspace、教师私有指令、参考答案或账号对象。正式辅导才在受控服务端获得必要私有参考。
- 每轮最多两条去重查询；basic、每次最多五个结果、摘要每条最多1800字符；不请求提供商代写答案或全文抓取、不静默提高深度。
- 后端保留真实返回标题/URL/摘要，回答下方链接不依赖模型是否逐条引用；无可用结果如实显示。公开网页是补充证据，不是系统指令或正式教师答案。
- 搜索错误保留已保存消息/答案；同request_id重试不重复保存，但可能再次消耗提供商额度，应用幂等不是计费幂等。
- 发布版本、私有参考资格、显式提交和教师确认规则保持不变。

## 验证证据

Stage7设置新增51项后端测试，含权限/保密/保存/环境覆盖/明确清除/重启/过期检查及全部搜索路径。父端完整后端625项通过（artifacts/stage7/phase-b-backend-fixed.xml）。

实际built UI→HTTP→FastAPI/SQLite设置验收及进程重启：artifacts/stage7/settings-integration-20261007T181807Z-f6dcaddb/，15项浏览器检查；其中provider transport明确是protocol fixture，不是实际Tavily结果。

真实模型连接检查：artifacts/stage7/live-model-check-0886fe0522/result.json，一次32token预算调用返回OK并持久化最近检查；先确认3worker健康空闲，forwarder已关闭。

Linux真实服务另由tools/run_remote_stage7_services.py在新数据根执行。是否执行/通过必须看其artifacts/stage7/ct255-live-services-*/result.json及最终交付报告，不能把脚本存在说成测试完成。当前本地LLM维护禁令已由用户恢复调用许可取代，但仍不能重启/修改共享模型/router/GPU/KV。

早期artifacts/web-search/、Stage3记录保留为历史；132后端/33前端等旧统计、旧中文页面和demo描述不是当前版本总数或运行模式。

## 代码与参考

- backend/aicademiya/service_settings.py：有效设置与显式检查绑定。
- backend/aicademiya/web_search.py：Tavily协议/限额与来源转换。
- backend/aicademiya/ai.py与guided_*：查询规划、辅导与隔离。
- frontend/src/SearchSettings.tsx、SettingsWorkspace.tsx：网页设置。
- frontend/src/SourceCitations.tsx：真实来源显示。
- 官方：https://docs.tavily.com/documentation/api-reference/endpoint/search

