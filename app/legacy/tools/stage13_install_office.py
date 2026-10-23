"""One-time, bounded server-side Office renderer installation; no model changes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,os,re,shutil,subprocess
PACKAGES=['libreoffice-impress','libreoffice-writer','fonts-crosextra-carlito','fonts-crosextra-caladea','fonts-liberation2','fonts-noto-cjk']
def main():
 if os.geteuid()!=0:raise SystemExit('Run with sudo in the interactive terminal; never send credentials to the agent.')
 now=datetime.now(timezone(timedelta(hours=8)))
 if now>=datetime(2026,10,11,12,30,tzinfo=now.tzinfo):raise SystemExit('Installation start window closed for this timeboxed task.')
 root=Path('/opt/aicademiya-documents');root.mkdir(exist_ok=True)
 env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='l',LC_ALL='C')
 plan=subprocess.check_output(['apt-get','-s','install','--no-install-recommends',*PACKAGES],env=env,text=True,timeout=90)
 (root/'office-install-plan.txt').write_text(plan)
 summary=re.search(r'(\d+) upgraded, (\d+) newly installed, (\d+) to remove',plan)
 if not summary or int(summary[1])or int(summary[3]):raise RuntimeError('Refusing unrelated package upgrade/removal; inspect the plan.')
 print(summary.group(0),flush=True)
 subprocess.run(['apt-get','-y','--no-install-recommends','-o','Acquire::Retries=1','-o','Acquire::http::Timeout=20','-o','Acquire::https::Timeout=20','install',*PACKAGES],env=env,check=True,timeout=1200)
 exe=shutil.which('libreoffice')or shutil.which('soffice');assert exe
 version=subprocess.check_output([exe,'--headless','--version'],env=env,text=True,timeout=30).strip()
 report={'status':'installed','executable':exe,'version':version,'packages':PACKAGES,'existing_packages_upgraded':0,'packages_removed':0,'model_services_modified':False,'completed_at':datetime.now(timezone.utc).isoformat()}
 (root/'office-install-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
