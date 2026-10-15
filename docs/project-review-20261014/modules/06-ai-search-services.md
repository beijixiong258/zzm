# 06 · AI提供者、搜索与连接状态

## 作用与入口

本模块提供OpenAI-compatible模型请求、可选Tavily检索和连接状态。管理员在 Settings → AI Model / Web Search 管理服务；学生和教师通过对话框选择本次是否搜索。

## 核心文件

| 文件 | 职责 |
|---|---|
| `ai.py:71–148` | DB/环境有效设置、公开状态、模型设置写入和检查失效 |
| `ai.py:111–126` | 本地router精确识别与服务器HMAC作用域 |
| `ai.py:150–202` | 非流式Chat Completions、超时、图片负载、真实失败 |
| `ai.py:204–260` | 用户主动启用后的公共检索规划、工具调用与来源保留 |
| `ai.py:262–335` | 私有当前参考、教师指令与稳定课程系统前缀 |
| `web_search.py:43–94` | Tavily请求、结果上限、实际URL与snippet投影 |
| `service_settings.py:31–103` | 检查绑定/配置generation、DB优先设置、显式清除key |
| `model_connection.py:12–58` | 共享30秒健康检查、60秒失效时间、配置变化排除旧结果 |
| `frontend/src/live-connection.tsx` | 界面周期检查与登录/可见性生命周期 |
| `tools/warm_aicademiya_prefix.py` | 管理员显式预热已发布且不含学生信息的稳定前缀 |

## 请求链

`已授权学习workspace → 选定edition/材料与题目 → 学习引擎构造消息 → Tutor.completion_message → CT255 loopback socket proxy → GPU router → 模型反馈 → 结构/引用校验 → 原request回执与消息保存`。

DB保存的模型设置覆盖环境默认。私有参考和教师材料留在服务端构造上下文，学生DTO经过独立投影。

本地router集成同时要求provider `aicademiya-router`、base URL `http://127.0.0.1:18280/v1`、model `AIcademiya-64kx3-Qwen3.8-27B`。这条精确分支使用600秒超时和安装secret派生的HMAC user scope。CT255通过本机socket proxy保持这一契约。

图像请求带真实image_url部分并关闭文本prompt cache，8MiB负载预算控制图片消息。当前视觉教学入口为一条，文本教学容量为三条。

## 搜索与状态的区别

- Search关闭：跳过检索准备和Tavily。
- Search打开：强制模型调用web_search，最多2个query，每次最多5个结果；检索来源独立保存并展示。
- 搜索规划接收公共材料与当前请求，教师私有答案/指令只在最终教学阶段加入。
- Tavily key仅在服务器使用。明确清除保存一个空覆盖，旧环境key不会自动重新出现。
- bootstrap和普通status读取只返回状态；authenticated `/api/ai/connection`触发轻量GET。
- 每30秒共享检查，返回检查时间和60秒失效时间；管理员Generation check另行验证真实生成。
- 服务错误保留已保存学习内容和请求状态，界面显示可处理的错误。

## 当前核验

本轮远端进程使用上述router/provider/model配置；router健康回读：teaching_capacity=3、vision_teaching_capacity=1、queue=0。网站demo关闭，学生注册关闭。

证据：`evidence/remote-production-readback.json`、`router-health-readback.json`。本轮核验采用health/status、配置和源码读取；生成与Tavily质量沿用Stage16/既有测试证据，范围见 `verification.md`。

## 问题与整理结论

- **P1：避免改URL丢集成。** 直接把有效模型URL改成GPU私有IP会退出HMAC/600秒的精确router分支；优先保留socket proxy。
- **P2：检索最小化依赖模型规划。** 代码对工具名、query长度和次数做校验；query内容隐私约束仍主要通过规划prompt表达。进一步工作可增加可验证的敏感字段处理，现有教师私有上下文分离应保留。
- **P2：文案集中说明状态层次。** configured、轻量可达和真实生成检查分别对应配置、网络和生成，报告采用这三个明确字段。

本地已回收的MiniCPM/Paddle实验权重不在当前应用请求链中。生产GPU权重、router和KV位于远端独立树，均保持原位。
