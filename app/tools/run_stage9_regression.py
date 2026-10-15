"""Preserve Stage8 lifecycle and Stage7 UI/service assertions at explicit Stage9 version/schema."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'artifacts/stage9'/('regression-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
    env=os.environ.copy();env.update(AICADEMIYA_QA_TARGET_API='0.8.0',AICADEMIYA_QA_TARGET_SCHEMA='7',AICADEMIYA_QA_BRAND_ASSET='/aicademiya-mark-light.svg',NODE_TLS_REJECT_UNAUTHORIZED='1')
    groups=[]
    for name,args in [('stage8-lifecycle',['tools/run_stage8_integration.py']),('stage7-workbench-settings',['tools/run_stage7_integration.py','--compose-settings'])]:
        r=subprocess.run([sys.executable]+args,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
        (out/(name+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
        record={'name':name,'status':'failed','assertions_retained':True,'api_version':'0.8.0','schema_version':7}
        try:
            last=json.loads(r.stdout.strip().splitlines()[-1]);actual=json.loads(Path(last['result']).read_text(encoding='utf-8'));record.update(result_handle=last['result'],acceptance=actual)
            assert r.returncode==0 and actual['status']=='passed' and actual['final_acceptance'];record['status']='passed'
        except Exception as e:record['error']=str(e)
        groups.append(record)
        (out/'result.json').write_text(json.dumps({'status':'running','groups':groups},indent=2),encoding='utf-8')
        print(json.dumps({'group':name,'status':record['status'],'result':record.get('result_handle'),'error':record.get('error')}),flush=True)
    report={'status':'passed' if all(g['status']=='passed' for g in groups) else 'failed','groups':groups,'all_baseline_scenarios_retained':True,'target_api':'0.8.0','target_schema':7}
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'result':str(out/'result.json')}))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
