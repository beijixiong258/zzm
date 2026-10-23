"""Aggregate Stage4 verified artifacts; generate an operator result report."""
from pathlib import Path
from datetime import datetime
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage4'
def load(path):return json.loads((OUT/path).read_text(encoding='utf-8'))
def junit(path):
 root=ET.parse(OUT/path).getroot();suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
 return {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
def main():
 cut=load('ct255-cutover-result.json');local=load('integration-20261007T051338Z-18dd2b7a/result.json');remote=load('ct255-qa-e39aa57875/result.json')
 prod=load('production-readback.json');browser=load('production/browser-readback.json');ocr=load('ocr/run-20261007T043643Z-116c3ce1/cpu-ocr-evidence.json');release=load('release-materials/AIcademiya_V2-20261007-materials.report.json')
 unit={k:junit(f) for k,f in [('backend','parent-backend.xml'),('frontend','parent-frontend.xml'),('exact_release','exact-release-tests.xml')]}
 assert all(r['status']=='passed' for r in (cut,local,remote,prod,browser))
 assert all(not(v['failures'] or v['errors'] or v['skipped']) for v in unit.values())
 assert all(g['owned_listener_closed'] and g['owned_server_stopped'] for g in local['groups'])
 assert all(g['qa_service_stopped'] for g in remote['groups']) and remote['qa_listener_closed']
 assert len(ocr['results'])==ocr['cases_total']==ocr['cases_accepted'] and all(r['accepted'] for r in ocr['results'])
 result={'status':'passed','url':prod['url'],'release':prod['release'],'api_version':prod['api_version'],'schema_version':4,'unit':unit,
  'local_checks':{g['name']:len(g['acceptance']['checks']) for g in local['groups']},'linux_checks':{g['name']:len(g['acceptance']['checks']) for g in remote['groups']},
  'cpu_ocr':{'cases':ocr['cases_total'],'accepted':ocr['cases_accepted'],'actual_ocr_calls':sum(len(r['observed_ocr_calls']) for r in ocr['results']),'network_attempts':len(ocr['network_connect_attempts']),'cpu_providers':ocr['cpu_providers']},
  'production_migration':cut['production_migration'],'pre_upgrade_counts':cut['pre_upgrade_counts'],'post_migration_counts':cut['post_migration_counts'],
  'backup':cut['backup'],'config_backup':cut['config_backup'],'restore_rehearsal':cut['restore_rehearsal'],'restore_records_and_files_match':cut['restore_result']['records_match'] and cut['restore_result']['files_match'],
  'maintenance_seconds':round((datetime.fromisoformat(cut['maintenance_ended_at'])-datetime.fromisoformat(cut['maintenance_started_at'])).total_seconds(),3),
  'release_files':release['file_count'],'production_static_files_verified':len(prod['static_files']),'anonymous_browser_verified':browser,
  'old_release_retained':cut['old_release'],'qa_services_stopped':True,'model_services_modified':cut['model_services_modified'],
  'evidence_boundaries':['Exact release tests overlap backend coverage.','This stage uses actual HTTP/SQLite/CPU OCR/Chrome/Edge but deterministic demo tutoring, not new real-model quality evidence.','Production browser readback was anonymous only; authenticated mutations were verified on isolated QA, not real learning records.','Same-container backup/restore is not off-host disaster recovery.']}
 (OUT/'final-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 report=f'''# AIcademiya Stage4：材料库与界面调整交付

## 已上线

网站：{prod['url']}/
Release：`{prod['release']}`；API`{prod['api_version']}`；数据库schema4。

当前操作者为朋友Z。全部实施/验收子任务已返回并由主会话验证；没有待执行后台任务。生产应用与原代理active，CT255保护/自启保留。生产演示登录关闭，匿名课程401；实际线上{len(prod['static_files'])}个静态文件与发布包逐项一致，匿名桌面/390px登录页与新Logo回读通过。

## 七项需求

| 项目 | 交付行为 |
|---|---|
| 多文件上传 | 一次选择多个文件，一个动作处理队列；显示逐文件结果，仅重试失败项。刷新失败不重传已确认上传的文件。离开页面停止尚未开始的队列项，已上传文件保留。 |
| Course / Session Materials | 文件属于课程库，每个Session只展示显式关联子集。S1=A/B/C，S2=B/D/E、课程库5份原件已在真实HTTP/SQLite和浏览器验证。复用同ID和原件，移出Session不删除课程库/其他Session/旧版本。 |
| PDF预览 | 默认新标签页Open authenticated preview；服务端移除阻断原生阅读器的PDF sandbox，保留鉴权、正确MIME和nosniff。Chrome/Edge均实际显示两页PDF与阅读器工具栏。 |
| 图片材料读取 | 独立材料也有native text +本地CPU OCR：PNG/JPEG/WebP、扫描/混合PDF、DOCX/PPTX嵌图和group/table文字。提供覆盖、失败/跳过、限额和提取文字；旧材料可显式Re-extract text / OCR。 |
| 输入快捷键 | Enter发送，Shift+Enter换行。修饰键、重复/空白/busy及IME组合确认不误发；失败重试ID和草稿规则保留。 |
| Quiz去重 | 保留反馈和单张结构化题目/选项卡，移除准确匹配的重复presentation；原始消息/导出不改写。 |
| Logo | 保留参考人物/拱门/装饰轮廓，底部换成打开的书本。绿色/白色详细版本、小尺寸简化版及favicon均生成和实际渲染检查。 |

### 使用要点

- 教师在Session Materials上传，或从Course Materials下拉选择已有文件。
- 标题、可见性、提取结果是共享文件属性，编辑影响关联的Session草稿；关联关系各自独立。
- 上传/关联/重提取后，仍需发布新course edition，学生才使用新版本。现有课程没有被自动发布或重提取，旧学习版本没有被覆盖。
- 保留teacher-only/answer-key权限，不因attach而公开；课程库不整体暴露给学生或传给导师。

### OCR和LLM的职责

平台先提取文档原生文字、拆解图片并做OCR，再把选定文字给LLM。纯文本LLM不必具备OCR能力即可利用这些文字；即使LLM本身支持视觉，平台仍须实现图像输入链路，模型才能看图。

**OCR不能保证理解图片的所有内容**：图表关系、颜色、复杂布局和隐藏/裁剪/动画内容不等于文字识别。当前未切换模型或加入新的视觉推理链路。提取有真实限额：单文件25MiB，Office展开100MiB，200 native units，64 OCR尝试，16MP原图、约4MP OCR raster，excerpt最多50000字符；具体跳过范围在Coverage notes中。每轮导师上下文仍为有界选段，不声称整门课程的每个字符都被读入。

本轮实际OCR识别中曾出现“别/別”差异，原始证据保留；需要教师复核，不以Ready或完成数量冒称识别百分百正确。

## 验收

- 后端完整：{unit['backend']['tests']} passed；前端完整：{unit['frontend']['tests']} passed；TypeScript/Vite构建通过。
- 精确发布档案：{unit['exact_release']['tests']} passed，{release['file_count']}个文件；该suite与后端覆盖有重叠，不相加。
- 本地真实HTTP/SQLite：API{result['local_checks']['api']}项、浏览器{result['local_checks']['browser']}项，0失败，数据完整性/FK/schema4检查通过。
- CT255暂存Linux/LAN：API{result['linux_checks']['api']}项、浏览器{result['linux_checks']['browser']}项，0失败；实际CPU OCR及重提取、重启成员关系、5份原件未复制均通过。
- 离线OCR合成语料：{ocr['cases_total']}例/{ocr['cases_accepted']}通过，{result['cpu_ocr']['actual_ocr_calls']}次实际OCR，3个ONNX session都仅CPU，网络连接尝试0。
- 浏览器键盘/组合事件、Chrome/Edge PDF、390px与品牌检查是真实浏览器；IME为组合事件模拟，不冒称人工OS输入法验证。
- 导师流程为明确的demo/protocol验收，本轮未新增真实LLM或搜索调用，不拿它评价模型教学质量。

## 生产数据与恢复

迁移前暂停写入，原有{cut['production_migration']['original_tables']}张应用表按原列/原行逐项对比，全部保持；SQLite integrity=ok、外键问题0。原有3账号、15材料、24消息、9条guided请求、2个guided run和旧课程/答案/修订均保留。新增15条课程归属与15条session成员关系，无账号密码、安装secret或模型配置重置。

- 数据备份：`{cut['backup']}`
- 配置备份：`{cut['config_backup']}`
- 已验证恢复副本：`{cut['restore_rehearsal']}`（禁模型/搜索）
- 保留旧代码：`{cut['old_release']}`
- 记录的维护窗口：{result['maintenance_seconds']}秒。

恢复副本使用即时synthetic账号实际注册/登录、读取课程及下载材料，并跑新材料CPU OCR。未读取/重新输入真实密码，未把验收用户/答案写入生产。这是同容器恢复验证，不是异地灾备。所有QA服务/监听已停止；模型/路由/GPU/KV与公网入口未改。

## 证据入口（相对app）

- artifacts/stage4/final-verification.json
- artifacts/stage4/ct255-cutover-result.json
- artifacts/stage4/production-readback.json、production/browser-readback.json
- artifacts/stage4/parent-backend.xml、parent-frontend.xml、exact-release-tests.xml
- artifacts/stage4/integration-20261007T051338Z-18dd2b7a/
- artifacts/stage4/ct255-qa-e39aa57875/
- artifacts/stage4/ocr/run-20261007T043643Z-116c3ce1/
- artifacts/stage4/release-materials/
- artifacts/stage4/brand/preview.html

早期harness失败、pre-final partial和原参考图均保留；当前结论基于最终严格总验收，不抹去历史失败。部署前源码快照见artifacts/stage4/baseline.json。
'''
 (ROOT/'DEPLOYMENT_STAGE4_RESULT.md').write_text(report,encoding='utf-8')
 print(json.dumps({'status':result['status'],'unit':unit,'local':result['local_checks'],'linux':result['linux_checks'],'maintenance_seconds':result['maintenance_seconds'],'report':str(ROOT/'DEPLOYMENT_STAGE4_RESULT.md')},ensure_ascii=False))
if __name__=='__main__':main()
