"""Aggregate source-backed Stage7 completion evidence and write the delivery report."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stage7'
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def junit(name):
 r=ET.parse(OUT/name).getroot();s=[r] if r.tag=='testsuite' else list(r.iter('testsuite'))
 return {k:sum(int(x.get(k,0)) for x in s) for k in ('tests','errors','failures','skipped')}
def main():
 cut=load('ct255-cutover-result.json');qa=load('qa-handoff/run-20261007T194357Z-5292d62a/result.json');linux=load('ct255-qa-e0c8a9ea59/result.json');live=load('ct255-live-services-0a2aa38ece/result.json');prod=load('production-readback.json');ui=load('production/browser-readback.json');release=load('release-clarity/AIcademiya_V2-20261008-clarity.report.json')
 units={'backend':junit('parent-final-backend.xml'),'frontend':junit('parent-final-frontend.xml'),'exact_archive':junit('exact-release-tests.xml')}
 assert all(r['status']=='passed' for r in (cut,qa,linux,live,prod,ui)) and qa['final_acceptance'] and qa['source_dist_stable_during_run']
 assert all(not any(v[k] for k in ('errors','failures','skipped')) for v in units.values())
 direct={g['name']:len(g['acceptance']['checks']) for g in qa['groups'] if g['name']!='composed-parent-settings-browser-api-restart'}
 composed=next(g['acceptance'] for g in qa['groups'] if g['name']=='composed-parent-settings-browser-api-restart')
 direct['settings_browser_api_restart']=len(composed['groups'][0]['browser']['checks'])
 assert sum(direct.values())==qa['verified_check_count']
 for group in qa['groups']:
  assert group['status']=='passed'
  if group['name']=='composed-parent-settings-browser-api-restart':
   assert all(g['owned_server_stopped'] and g['owned_listener_closed'] for g in group['acceptance']['groups'])
  else:assert group['owned_server_stopped'] and group['owned_listener_closed']
 assert linux['qa_listener_closed'] and all(g['qa_service_stopped'] for g in linux['groups']) and live['owned_qa_service_stopped']
 old=json.loads((ROOT/'artifacts/stage6/release-workbench/AIcademiya_V2-20261007-workbench.manifest.json').read_text())['files'];new=load('release-clarity/AIcademiya_V2-20261008-clarity.manifest.json')['files']
 marks=['aicademiya-mark.svg','aicademiya-mark-small.svg','aicademiya-mark-light.svg','favicon.svg','favicon.ico','favicon-32.png','favicon-48.png','apple-touch-icon.png']
 assert all(old['frontend/dist/'+p]['sha256']==new['frontend/dist/'+p]['sha256'] for p in marks)
 seconds=round((datetime.fromisoformat(cut['maintenance_ended_at'])-datetime.fromisoformat(cut['maintenance_started_at'])).total_seconds(),3)
 deployed=datetime.fromisoformat(cut['maintenance_ended_at']).astimezone(timezone(timedelta(hours=8))).isoformat()
 result={'status':'passed','url':prod['url'],'release':prod['release'],'api_version':'0.6.0','schema_version':5,'deployed_at_cst':deployed,'unit':units,'local_acceptance':direct,'verified_local_checks':sum(direct.values()),'linux_acceptance':{g['name']:len(g['acceptance']['checks']) for g in linux['groups']},'staged_real_service_tests':live['bounded_application_calls'],'staged_service_check_restart':live['checks'][-1],'local_real_model':load('live-model-check-0886fe0522/result.json')['status'],'local_real_search':load('live-search-check-afddfbbfc7/result.json')['status'],'v4_brand_files_unchanged':len(marks),'original_data_preservation':cut['production_migration'],'pre_upgrade_counts':cut['pre_upgrade_counts'],'post_upgrade_counts':cut['post_migration_counts'],'backup':cut['backup'],'config_backup':cut['config_backup'],'restore_rehearsal':cut['restore_rehearsal'],'old_release':cut['old_release'],'maintenance_seconds':seconds,'release_files':release['file_count'],'static_production_files_verified':len(prod['static_files']),'qa_services_stopped':True,'production_model_infrastructure_changed':False,'boundaries':['Unit/archive/browser/fixture checks overlap; no fabricated unique grand total.','Linux external lane excludes local-only delay/fail-once/provider transport instrumentation; actual service checks separately verified.','Production browser verification was anonymous/read-only; authenticated mutations used isolated synthetic data.','Selected computed contrast/token checks and keyboard/mobile checks are not full WCAG certification.','CSS/equivalent reflow is not native browser zoom; composition simulation is not an OS IME test.','Historical/QA recorded demo content was not falsely relabelled live; normal production offers no demo mode.']}
 (OUT/'final-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 text=f'''# Stage7交付：Clarity界面与Settings

## 已完成并上线

- 网站：{prod['url']}/
- 发布：`{prod['release']}`，API0.6.0/schema5。
- 切换验证完成时间：{deployed}（中国标准时间）。
- PVE192.168.10.16 CT255 aicademiya-v2；current指向新release。应用/模型代理active，保护/onboot保留，英文描述已更新回读；没有修改GPU/router/KV或网络入口。

本轮按照Z授权完成三个阶段：代表页预览 → Settings/导航/服务配置 → 全站推广、验证及保留数据上线。不是仅提交设计稿。

## 交付内容

### 信息架构与视觉

- Course Home / My Learning / Settings作为一级目的地；课程材料、Learners、Publish & versions回归课程层，课次只保留Teaching setup / Materials / Questions & answers / Student work。
- 教学目标和Instructions/导入、反馈策略、流程优先；背景、低频高级选项、时段安排、来源技术信息及preview revision按需展开。必要的未保存/过期/错误/当前开放状态仍显式显示。
- 帮助可鼠标悬停、键盘focus/Enter/Escape及触摸点击；支持移入提示阅读、移开/转移焦点关闭。品牌真实链接返回Course Home，未保存表单可取消离开；浏览器hash导航和改密/配置草稿也受保护。
- 全局token原位统一：暖白内容底、深正文、森林绿主操作、蓝色信息/链接/焦点、琥珀提醒、红色错误；不以颜色单独传达状态。serif用于品牌/页面/课程标题，sans用于表单/阅读/数据；正文、标签和辅助文字层级区分。
- 保留V4图案及{len(marks)}个原图标资源原字节；以40px导航展示检查清晰度，没有另行重画或为加粗破坏细节。
- canonical CourseLibrary提供真实文件/课次关系、过滤、私有标记、下载/预览和Manage in session入口；没有虚构课程级上传API。
- 学生聊天阅读优先，保存回复/记录/来源等为辅助入口；手机自然高度修复发送区裁切，原文/修订导航可达。提交、教师确认、讨论和model outcome不混为成绩。
- 统一Save draft、Preview tutor、Tutor preview、Import instructions等自然英文；修正question单复数和重复draft标题。原始模型消息/导出不因UI简化被重写。

### Settings与实际服务

- Account对所有角色开放；AI Model / Web Search / User Management只对admin挂载和发请求，后端仍强制权限。头像保留账户快捷入口，旧profile/accounts路线兼容。
- 正常产品不再提供Feedback/Demo切换或演示登录；生产即便旧配置mode=demo也不执行模拟回答。未配置/服务故障真实报错，无静默兜底。历史或隔离QA消息仍保留真实Recorded demo/fixture标记，未伪装成实模。Windows正常start.cmd也不再默认开启demo；开发测试adapter保留。
- Tavily在Settings → Web Search真实保存：允许搜索、替换key、明确清除、独立GET回读、显式测试。环境配置兼容保留；保存覆盖在SQLite，明确清除会抑制旧环境key重现。key不回显、不写浏览器存储、不进入错误/日志；逐轮Web search默认关闭，保存/打开页面不自动调用服务。
- Active AI Model显示配置模型及事实状态。Configured不等于Connected；记录最近显式检查与时间，配置变更失效，过期并发检查409。父端另修复“旧检查成功遮盖当前运行错误”，不伪造失败时间或旧绿灯。

## 验证

| 层级 | 实际结果 |
|---|---|
| 全后端 | {units['backend']['tests']}通过，0失败/跳过 |
| 全前端 | {units['frontend']['tests']}通过，0失败/跳过；完整TS/Vite生产构建通过 |
| 精确归档 | {units['exact_archive']['tests']}通过；{release['file_count']}文件，代码{release['component_counts']['code']}、私有seed{release['component_counts']['private_seed']} |
| 本地真实应用链路 | {sum(direct.values())}检查：API{direct['api']}、正常runtime禁demo HTTP gate{direct['production-demo-http-gate']}、浏览器{direct['browser']}、Settings/SQLite/进程重启{direct['settings_browser_api_restart']}；strict current dist，final_acceptance=true |
| Linux暂存实际HTTP/浏览器 | API{result['linux_acceptance']['api']}、浏览器{result['linux_acceptance']['browser']}通过，远端SQLite schema5/integrityok/FK0 |
| 真实服务 | Windows各1次模型/Tavily连接检查通过；CT255暂存各1次模型/Tavily检查通过，实际Linux重启后检查结果/时间保持，无重复probe |
| 上线回读 | {len(prod['static_files'])}个静态文件逐项匹配发布清单；health200、匿名course401、demo403、API0.6、匿名桌面/390px登录页与品牌链接通过 |

原型/独立组件fixtures另有浏览器和单测证据，不与上述测试简单累加成“独立总数”。Linux外部运行没有复制本地fault/control桩场景；provider真实调用证据与protocol fixture严格分开。未向生产加入测试账号/学习记录，也未使用真实账号密码登录测试。

## 数据保护与恢复

升级暂停写入时，原{cut['production_migration']['original_tables']}张应用表的原列/原行逐项校验保留；teacher preview generation、已发布版本、材料关系、用户/密码/登录会话、原始消息和安装secret均保留。schema仍5；服务设置使用已有settings/meta，不重建数据库，不自动发布课程或重提取材料。

维护窗口记录为{seconds}秒。先完成最终备份、恢复到独立目录、数据/文件校验、Linux启动/合成账号登录/下载/CPU OCR演练，才切换current。恢复副本明确清空模型URL/model/key并覆盖关闭搜索，未从共享namespace发模型请求。

- 数据备份：`{cut['backup']}`
- 配置备份：`{cut['config_backup']}`
- 恢复演练：`{cut['restore_rehearsal']}`
- 保留旧代码：`{cut['old_release']}`

这是同容器恢复演练，不是异地灾备。旧版本不认识新搜索覆盖语义，因此回滚需匹配代码/数据/私有配置，不能仅凭schema未变直接换回链接。历史材料引用的旧release继续保留。

## 已解决的问题及证据边界

- service_settings模块及SettingsWorkspace/CourseLibrary新编译chunk必须入显式发布allowlist；初期package失败保留，最终完整与精确包均通过。
- 源码/页面改版后旧文案和折叠控件选择器需更新；保持数据、身份、权限、private与retry断言，不用改产品迎合旧截图。
- pending fixture改成有界hold/release并等待真实server reservation，避免2秒固定延迟竞态；不是放松生产pending guard。
- Chrome一次本地与一次旧production截图命令等待绘制超时；冻结动画、隐藏光标并使用有界截图时间后通过，没有为截图失败回滚已验证服务。失败运行保留。
- 键盘/手机/部分颜色对比验证不是完整WCAG认证；重排/CSS zoom不是原生缩放，composition事件不是OS输入法实测。真实连接检查证明服务与状态链路，不是重新评估所有教学质量。

## 证据入口

- STAGE7_UX_PROPOSAL.md、STAGE7_CONTRACT.md、STAGE7_CHECKPOINT.md
- artifacts/stage7/final-verification.json、ui-review.html
- artifacts/stage7/parent-final-backend.xml、parent-final-frontend.xml、exact-release-tests.xml
- artifacts/stage7/qa-handoff/run-20261007T194357Z-5292d62a/result.json（引用当次Settings组合结果）
- artifacts/stage7/ct255-qa-e0c8a9ea59/result.json
- artifacts/stage7/ct255-live-services-0a2aa38ece/result.json
- artifacts/stage7/ct255-cutover-result.json、production-readback.json、production/
- artifacts/stage7/release-clarity/（最终实际部署清单）

初始未分发的pre-copy-polish包保留在release-clarity-before-copy-polish；最终82文件清单与21个线上资源回读绑定实际部署字节，不能用初始包替换。本轮所有委派和自有QA服务/浏览器/forwarder已收尾，无待交后台工作。当前操作者仍是朋友Z，不将本轮教学材料或合成答案归入账号原主人的个人经历。
'''
 (ROOT/'DEPLOYMENT_STAGE7_RESULT.md').write_text(text,encoding='utf-8')
 shots=[('Before · Stage6 teacher editor','../stage6/integration-20261007T151825Z-322f7b25/browser/desktop-workbench.png'),('After · Stage7 teacher editor','qa-handoff/run-20261007T194357Z-5292d62a/browser/stage7-natural-teacher-collapsed.png'),('Course materials · real memberships','qa-handoff/run-20261007T194357Z-5292d62a/browser/stage7-course-library-memberships.png'),('Mobile · tutor conversation','qa-handoff/run-20261007T194357Z-5292d62a/browser/stage7-student-mobile-workspace.png')]
 for _,p in shots:assert (OUT/p).is_file()
 html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AIcademiya · Stage7 UI review</title><style>body{margin:0;background:#f6f7f3;color:#23352e;font:16px/1.6 "Segoe UI",sans-serif}header{padding:32px;max-width:1300px;margin:auto}h1{font-family:Georgia,serif}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;padding:0 32px 40px;max-width:1500px;margin:auto}figure{margin:0;background:white;border:1px solid #dce4df;border-radius:12px;padding:18px}figcaption{font-weight:600;margin-bottom:15px}img{display:block;width:100%;height:auto;max-height:1100px;object-fit:contain;object-position:top}a{color:#355c98}@media(max-width:760px){main{grid-template-columns:1fr;padding:16px}}</style><header><h1>AIcademiya · Clarity</h1><p>真实构建界面的前后对照。使用独立合成QA课程，图中的fixture/Recorded demo不代表生产模式；没有生成或重绘界面。</p><p>网站已上线：<a href="http://192.168.32.55:18773/">Course Home</a> · API0.6.0。完整验证与限制见DEPLOYMENT_STAGE7_RESULT.md。</p></header><main>'''+''.join(f'<figure><figcaption>{name}</figcaption><a href="{url}"><img src="{url}" alt="{name}"></a></figure>' for name,url in shots)+'</main></html>'
 (OUT/'ui-review.html').write_text(html,encoding='utf-8')
 print(json.dumps({'status':'passed','unit':units,'local_checks':result['verified_local_checks'],'linux':result['linux_acceptance'],'maintenance_seconds':seconds,'static_files':len(prod['static_files']),'report':str(ROOT/'DEPLOYMENT_STAGE7_RESULT.md'),'review':str(OUT/'ui-review.html')},ensure_ascii=False))
if __name__=='__main__':main()
