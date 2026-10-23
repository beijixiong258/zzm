"""Aggregate final Stage6 source-backed acceptance and deployment evidence."""
from pathlib import Path
from datetime import datetime
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/stage6'
def load(p):return json.loads((OUT/p).read_text(encoding='utf-8'))
def junit(p):
 r=ET.parse(OUT/p).getroot();s=[r] if r.tag=='testsuite' else list(r.iter('testsuite'))
 return {k:sum(int(v.get(k,0)) for v in s) for k in ('tests','failures','errors','skipped')}
def main():
 cut=load('ct255-cutover-result.json');local=load('integration-20261007T151825Z-322f7b25/result.json');remote=load('ct255-qa-5fcf9054a0/result.json');live=load('live-teacher-e00ce25d2a/result.json');prod=load('production-readback.json');browser=load('production/browser-readback.json');release=load('release-workbench/AIcademiya_V2-20261007-workbench.report.json')
 unit={k:junit(p) for k,p in [('backend','parent-backend.xml'),('frontend','parent-frontend.xml'),('exact_release','exact-release-tests.xml')]}
 assert all(r['status']=='passed' for r in (cut,local,remote,live,prod,browser))
 assert all(not(v['failures'] or v['errors'] or v['skipped']) for v in unit.values())
 assert all(g['owned_server_stopped'] and g['owned_listener_closed'] for g in local['groups'])
 assert all(g['qa_service_stopped'] for g in remote['groups']) and remote['qa_listener_closed'] and live['owned_forwarder_stopped']
 old=json.loads((ROOT/'artifacts/stage5/release-logo-v4/AIcademiya_V2-20261007-logo-v4.manifest.json').read_text())['files'];new=load('release-workbench/AIcademiya_V2-20261007-workbench.manifest.json')['files']
 marks=['aicademiya-mark.svg','aicademiya-mark-small.svg','aicademiya-mark-light.svg','favicon.svg','favicon.ico','favicon-32.png','favicon-48.png','apple-touch-icon.png']
 assert all(old['frontend/dist/'+p]['sha256']==new['frontend/dist/'+p]['sha256'] for p in marks)
 seconds=round((datetime.fromisoformat(cut['maintenance_ended_at'])-datetime.fromisoformat(cut['maintenance_started_at'])).total_seconds(),3)
 result={'status':'passed','url':prod['url'],'release':prod['release'],'api_version':'0.5.0','schema_version':5,'unit':unit,'local_checks':{g['name']:len(g['acceptance']['checks']) for g in local['groups']},'linux_checks':{g['name']:len(g['acceptance']['checks']) for g in remote['groups']},'real_model':{k:live[k] for k in ('application_turns','model_requests','source_preview_matches_actual_request','stale_rejected_without_inference','new_saved_instruction_reached_model','owned_forwarder_stopped')},'brand_unchanged':True,'production_original_rows':cut['production_migration'],'pre_upgrade_counts':cut['pre_upgrade_counts'],'post_migration_counts':cut['post_migration_counts'],'backup':cut['backup'],'config_backup':cut['config_backup'],'restore_rehearsal':cut['restore_rehearsal'],'maintenance_seconds':seconds,'release_files':release['file_count'],'production_static_files_verified':len(prod['static_files']),'qa_services_stopped':True,'model_configuration_changed':False,'boundaries':['Exact release suite overlaps backend coverage.','Linux external QA does not repeat the local-only injected delay/fail-once scenarios.','The first workspace GET may create an empty operational row; it does not save teaching content, bind/reset a preview or invoke inference.','Real warmup response included an extra question; passed integration is not perfect teaching-quality evidence.','Production browser readback was anonymous; authenticated mutations were tested on isolated data.']}
 (OUT/'final-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 text=f'''# Stage6交付：教师工作台、来源复核与学习过程概览

## 已上线

网站：{prod['url']}/
Release：`{prod['release']}`；API0.5.0/schema5。PVE192.168.10.16 CT255，`/opt/aicademiya/current`已切换。应用/代理active、保护和onboot保留，demo登录关闭。线上{len(prod['static_files'])}个静态文件逐项匹配实际发布包，匿名桌面/390px登录页回读通过。用户选定V4图标8个文件未变。

## 用户可见结果

1. **同屏配置与草稿试聊**：左侧课程配置，右侧Draft test chat；手机可回跳。打开不自动调用模型；Start/Resume为显式动作。未保存编辑不冒充试聊依据。
2. **保存版与测试身份**：保存内容变动使旧测试stale，须明确Reset my preview。重置只清本人、本session、当前draft测试，拒绝pending请求，学生/其他账户/历史版本不受影响。既有旧教师试聊不在迁移时自动清空，可先导出再重置。
3. **指令与来源复核**：按保存题目/阶段查看编译指令、真实材料ID、实际片段、私有当前reference、角色/排除原因、OCR覆盖与截断。实际使用字符与容量分开显示；60000 UTF8字节是整个live request上限，不是预览已用字节或全文读入证明。
4. **指令文件导入**：原生/CPU提取后可检查编辑、Append/Replace，再Apply到未保存Additional instructions。保留其他dirty字段，不自动附件入库、保存或发布；30000合并上限超出会阻止应用，不悄悄截断。未虚构参考存档缺失的S6 DOCX。
5. **教师过程事实**：当前阶段、保存答复/修订、明确guided帮助、讨论状态和最新formative outcome；可以定位准确原消息或修订记录。未知过去结果不重建，讨论不等于教师确认，不生成参与度/掌握评分或全班AI摘要。

紧凑试聊不提供正式提交/教师确认。完整学习预览保留，并已补齐reading/answer/reference-reveal/submit的preview_id查询参数。缺失/旧ID/保存revision过期返回409，不通过静默放行绕过身份。旧non-guided chat仍不能操作managed preview。

## 使用顺序

Configuration里编辑或Review instruction file导入 → Apply到未保存草稿 → Save content draft → 若已有测试则Reset my preview → Start/Resume preview。发布仍是单独操作，不会因为试聊/导入自动改变学生课程。

学习记录中打开某学生后，Process overview与原对话并排。Locate latest reply定位真实原文，Responses & revisions查看历史作答；正式教师review状态仍独立。

## 验收与实模

- 完整后端{unit['backend']['tests']}通过、完整前端{unit['frontend']['tests']}通过，0失败/跳过；最终TypeScript/Vite构建通过。
- 精确归档{unit['exact_release']['tests']}项通过，{release['file_count']}个发布清单文件。与后端覆盖有重叠，不累加。
- 本地实际HTTP/SQLite：API{result['local_checks']['api']}项、浏览器{result['local_checks']['browser']}项；无app route interception，独立数据，schema5/integrity/FK正常。
- CT255 Linux/LAN：API{result['linux_checks']['api']}项、浏览器{result['linux_checks']['browser']}项；原生DOCX/TXT/PDF、导入/保存/过期/重置/完整预览/过程导航通过。远端没有重复本地独占的delay/fail-once注入；不将其误记为同样数量。
- 真实本地模型：{live['application_turns']}应用交互/{live['model_requests']}真实模型请求，错答、求助、正确+混合追问、来源预览与真实provider payload精确相等、stale409不推理、重置后新指令进入模型通过。调用前检查3worker空闲健康，未修改模型/router/GPU/KV/provider配置；forwarder已停止。

实模仍有措辞局限：一次warmup过渡额外问了一个问题，随后应用又展示了canonical worksheet题；部分回复略长。记录在`artifacts/stage6/live-model-observations.md`，没有用删文本或demo兜底掩盖，不把这次集成通过称作零缺陷教学质量。

首次workspace GET沿用现有行为，会创建空workspaces操作行；不是严格“零数据库写”。来源/指令提取等pure端点另有全表不变验证。打开pane不自动保存教学内容、不绑定/清空试聊、不自动推理。

## 数据与恢复

升级时原{cut['production_migration']['original_tables']}张应用表的原列/原行逐项不变；新增teacher_previews表为空，不自动绑定或reset。账号、25条旧消息、10条guided请求、旧版本和记录保留。SQLite integrity=ok，外键问题0。记录维护窗口{seconds}秒。

- 数据备份：`{cut['backup']}`
- 配置备份：`{cut['config_backup']}`
- 已验证恢复副本：`{cut['restore_rehearsal']}`（模型/搜索禁用）
- 保留旧代码：`{cut['old_release']}`

恢复副本实际synthetic注册/密码登录、课程和材料读取及Linux CPU OCR通过。新preview表没有文件路径；全部表/schema随既有backup工具保存。未向生产加入测试账户/作答，未自动修改或发布真实课程。所有QA服务/浏览器/forwarder结束。以上是同容器恢复演练，不是异地灾备。

## 证据（相对app）

- artifacts/stage6/final-verification.json
- artifacts/stage6/parent-backend.xml、parent-frontend.xml、exact-release-tests.xml
- artifacts/stage6/integration-20261007T151825Z-322f7b25/
- artifacts/stage6/ct255-qa-5fcf9054a0/
- artifacts/stage6/live-teacher-e00ce25d2a/
- artifacts/stage6/ct255-cutover-result.json、production-readback.json、production/
- artifacts/stage6/release-workbench/
- STAGE6_CONTRACT.md、STAGE6_CHECKPOINT.md

当前操作者仍为朋友Z；没有把本轮资料、测试答案或偏好归入账号原主人的个人经历。
'''
 (ROOT/'DEPLOYMENT_STAGE6_RESULT.md').write_text(text,encoding='utf-8')
 print(json.dumps({'status':'passed','unit':unit,'local':result['local_checks'],'linux':result['linux_checks'],'real_model':result['real_model'],'maintenance_seconds':seconds,'backup':cut['backup'],'report':str(ROOT/'DEPLOYMENT_STAGE6_RESULT.md')},ensure_ascii=False))
if __name__=='__main__':main()
