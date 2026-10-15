"""Run all preserved Stage7 regression assertions against explicit Stage8 API/schema/brand."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'artifacts/stage8'/('regression-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
 env=os.environ.copy();env.update(AICADEMIYA_QA_TARGET_API='0.7.0',AICADEMIYA_QA_TARGET_SCHEMA='6',AICADEMIYA_QA_BRAND_ASSET='/aicademiya-mark-light.svg')
 r=subprocess.run([sys.executable,'tools/run_stage7_integration.py','--compose-settings'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
 (out/'runner.log').write_text(r.stdout+'\n'+r.stderr,encoding='utf-8')
 report={'status':'failed','suite':'Stage7 assertions retained under explicit Stage8 version/schema/brand target','api_version':'0.7.0','schema_version':6,'source_changed_for_presentation_only':True}
 try:
  last=json.loads(r.stdout.strip().splitlines()[-1]);record=json.loads(Path(last['result']).read_text(encoding='utf-8'));report.update(result_handle=last['result'],acceptance=record)
  assert r.returncode==0 and record['status']=='passed' and record['final_acceptance'];report['status']='passed'
 except Exception as e:report['error']=str(e)
 (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'error':report.get('error')}));return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
