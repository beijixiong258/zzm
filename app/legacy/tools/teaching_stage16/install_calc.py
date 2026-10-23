"""Add the missing same-version Calc component; never upgrade existing packages.
Run only via the owner's masked sudo terminal. No service/model/worker changes.
"""
import argparse,json,os,re,subprocess
from pathlib import Path

EXPECTED={'libreoffice-calc','libreoffice-uiconfig-calc','libsuitesparseconfig7','libcolamd3','lp-solve'}
def packages():
 r=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n'],capture_output=True,text=True,check=True)
 return {line.split('\t')[0]:line.split('\t')[1] for line in r.stdout.splitlines()if line.split('\t')[-1].startswith('ii')}
def main():
 p=argparse.ArgumentParser();p.add_argument('--version',required=True);a=p.parse_args();assert os.geteuid()==0,'Use the masked sudo prompt, never chat or an environment password'
 root=Path(__file__).resolve().parent;before=packages();assert before.get('libreoffice-core')==a.version
 command=['apt-get','--no-install-recommends','--no-upgrade','-o','Acquire::Retries=0','-o','DPkg::Lock::Timeout=30','install','libreoffice-calc='+a.version]
 plan=subprocess.run([*command[:1],'-s',*command[1:]],env=dict(os.environ,LC_ALL='C'),capture_output=True,text=True,check=True);(root/'apt-plan.log').write_text(plan.stdout+plan.stderr)
 lines=re.findall(r'^Inst .*$',plan.stdout,re.M)
 matches=[re.match(r'Inst (\S+) \((\S+) ',line)for line in lines]
 assert all(matches),'Only new-package plan entries are allowed, not upgrade/reinstall entries'
 changes={m[1]:m[2]for m in matches}
 assert set(changes)<=EXPECTED,changes
 assert not re.search(r'^Remv ',plan.stdout,re.M),'Unexpected package removal'
 assert all(old==version for name,version in changes.items()for key,old in before.items()if key==name or key.startswith(name+':')),'An existing package would be upgraded'
 result={'status':'running','expected_core_version':a.version,'planned_new_packages':changes,'service_restart_requested':False}
 (root/'result.json').write_text(json.dumps(result,indent=2))
 print('Install missing Calc component only; no existing package upgrades or service restarts.',flush=True)
 env=dict(os.environ,DEBIAN_FRONTEND='noninteractive',NEEDRESTART_MODE='l')
 r=subprocess.run([*command[:1],'-y',*command[1:]],env=env,capture_output=True,text=True,timeout=600)
 (root/'apt-install.log').write_text(r.stdout+r.stderr)
 after=packages();unchanged=all(after.get(name)==version for name,version in before.items())
 result.update(returncode=r.returncode,existing_packages_unchanged=unchanged,new_packages={k:v for k,v in after.items()if k not in before},calc_version=after.get('libreoffice-calc'),filter_present=Path('/usr/lib/libreoffice/program/libscfiltlo.so').is_file())
 result['status']='passed'if r.returncode==0 and unchanged and result['calc_version']==a.version and result['filter_present']else'failed'
 (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
 return 0 if result['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())
