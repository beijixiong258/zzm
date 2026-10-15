"""Aggregate actual stage3 evidence; no remote calls or production changes."""
from pathlib import Path
from datetime import datetime
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
def load(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def junit(name):
 tree=ET.parse(ROOT/name).getroot();suites=[tree] if tree.tag=='testsuite' else list(tree.iter('testsuite'))
 return {key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
cut=load('artifacts/stage3/ct255-cutover-result.json')
local=load('artifacts/stage3/integration-20261006T161048Z-8234c46d/result.json')
remote=load('artifacts/stage3/ct255-qa-336414f46f/result.json')
live=load('artifacts/stage3/ct255-live-61ea667818/result.json')
flow=load('artifacts/stage3/live-spike-2625af6ce8/result.json')
readback=load('artifacts/stage3/production-readback.json')
release=load('artifacts/stage3/release-guided/AIcademiya_V2-20261007-guided.report.json')
result={'status':'passed','url':'http://192.168.32.55:18773/','release':'AIcademiya_V2-20261007-guided','api_version':'0.3.0',
'unit':{'backend':junit('artifacts/stage3/parent-final-backend.xml'),'frontend':junit('artifacts/stage3/parent-final-frontend.xml'),'exact_release':junit('artifacts/stage3/exact-release-tests.xml')},
'release_files':release['file_count'],'local_checks':{g['name']:len(g['acceptance']['checks']) for g in local['groups']},'linux_checks':{g['name']:len(g['acceptance']['checks']) for g in remote['groups']},
'live_model_flow':{'application_calls':flow['application_request_count'],'model_calls':flow['model_call_count'],'phases':[x['body']['tutor']['phase'] for x in flow['turns']]},
'linux_live_model_search':{'application_calls':len(live['turns']),'observed_router_request_delta':live['observed_router_request_delta'],'saved_sources':len(live['search_source_urls']),'saved_sources_mobile_verified':live['saved_ui']['mobile_source_reachable'],'new_inference_during_saved_ui':len(live['saved_ui']['new_tutor_requests'])},
'backup':cut['backup'],'private_config_backup':cut['config_backup'],'restore_rehearsal':cut['restore_rehearsal'],'restore_verified':cut['restore_result']['records_match'] and cut['restore_result']['files_match'],
'production_migration':cut['production_migration'],'original_counts':cut['pre_upgrade_counts'],'post_migration_counts':cut['post_migration_counts'],
'maintenance_seconds':round((datetime.fromisoformat(cut['maintenance_ended_at'])-datetime.fromisoformat(cut['maintenance_started_at'])).total_seconds(),3),
'production_readback':readback,'linux_cpu_ocr':cut['linux_cpu_ocr'],'old_release_retained':cut['old_release'],'all_remote_qa_services_stopped':all(g['qa_service_stopped'] for g in remote['groups']) and live['owned_qa_service_stopped'],
'notes':['Exact-release suite overlaps backend coverage; do not add the totals.','Demo/protocol fixtures are separate from actual model/search evidence.','Restored-copy password login used a runtime-generated synthetic account; real user hashes/sessions were preserved rather than re-entered.','Same-container restore rehearsal is not off-host disaster recovery.']}
assert all(v['failures']==v['errors']==v['skipped']==0 for v in result['unit'].values())
assert all(x['status']=='passed' for x in (cut,local,remote,live,flow,readback))
assert result['all_remote_qa_services_stopped'] and result['restore_verified']
(ROOT/'artifacts/stage3/final-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('notes','post_migration_counts','original_counts','production_readback','live_model_flow')},ensure_ascii=False,indent=2))
