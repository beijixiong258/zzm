"""Stage exact r6 release + separate same-ABI venv; no live service/config switch."""
from pathlib import Path
import hashlib,json,os,pwd,shutil,subprocess,sys
NAME='AIcademiya_V2-20261012-materials-r6'
QA=Path('/var/lib/aicademiya-qa/stage14-exact-r6')
SRC=QA/'extracted'/NAME;TARGET=Path('/opt/aicademiya/releases')/NAME
CURRENT=Path('/opt/aicademiya/current');OUT=QA/'release-stage-result.json'
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pyinfo(py):
 code="import sys,sysconfig,importlib.metadata as m,json;print(json.dumps({'version':list(sys.version_info[:3]),'purelib':sysconfig.get_path('purelib'),'packages':{d.metadata['Name'].lower():d.version for d in m.distributions()if d.metadata['Name']}}))"
 return json.loads(subprocess.check_output([str(py),'-B','-c',code],text=True))
def main():
 assert os.geteuid()==0 and not TARGET.exists();os.umask(0o022)
 old=CURRENT.resolve();user=pwd.getpwnam('aicademiya');manifest=json.loads((QA/(NAME+'.manifest.json')).read_text());assert manifest['release']==NAME
 for n,v in manifest['files'].items():assert sha(SRC/n)==v['sha256'],n
 assert sha(SRC/'backend/requirements.txt')==sha(old/'backend/requirements.txt'),'Dependency change requires separate installation review'
 previous=pyinfo(old/'.venv/bin/python');site=Path(previous['purelib']);assert not any(p.is_symlink()for p in site.rglob('*'));assert not list(site.glob('*.pth'))
 size=sum(p.stat().st_size for p in site.rglob('*')if p.is_file());assert shutil.disk_usage(TARGET.parent).free>size*2+1024**3
 shutil.copytree(SRC,TARGET)
 for p in [TARGET,*TARGET.rglob('*')]:
  os.chown(p,0,user.pw_gid)
  if p.is_dir():p.chmod(0o750)
  else:p.chmod(manifest['files'][p.relative_to(TARGET).as_posix()]['mode']|0o040)
 subprocess.run(['/usr/bin/python3','-m','venv','--without-pip',str(TARGET/'.venv')],check=True)
 own=pyinfo(TARGET/'.venv/bin/python');assert own['version']==previous['version'];shutil.copytree(site,Path(own['purelib']),dirs_exist_ok=True)
 copied=pyinfo(TARGET/'.venv/bin/python');assert copied['packages']==previous['packages']
 for p in [TARGET/'.venv',*(TARGET/'.venv').rglob('*')]:
  if p.is_symlink():continue
  os.chown(p,0,user.pw_gid);mode=p.stat().st_mode&0o777;p.chmod((mode&~0o022)|0o040|(0o010 if p.is_dir()or mode&0o111 else 0))
 check=subprocess.check_output([str(TARGET/'.venv/bin/python'),'-m','pip','check'],text=True);assert 'No broken requirements found'in check
 for n,v in manifest['files'].items():assert sha(TARGET/n)==v['sha256'],n
 data=QA/'staged-runtime-smoke';data.mkdir(mode=0o700);os.chown(data,user.pw_uid,user.pw_gid)
 code="from pathlib import Path;from backend.aicademiya.main import create_app;import backend.aicademiya.main as m;from fastapi.testclient import TestClient;assert Path(m.__file__).is_relative_to(Path("+repr(str(TARGET))+"));\nwith TestClient(create_app(data_dir=Path("+repr(str(data/'client'))+"),demo_enabled=True))as c:\n assert c.get('/api/health').status_code==200;assert c.post('/api/auth/demo',json={'role':'teacher'}).status_code==200;print('staged_actual_uid_app_boot_ok')"
 cmd=['runuser','-u',user.pw_name,'--','env','PYTHONPATH='+str(TARGET),'PYTHONDONTWRITEBYTECODE=1','AICADEMIYA_DATA_DIR='+str(data/'import'),'AICADEMIYA_AI_MODE=demo','AICADEMIYA_AI_BASE_URL=','AICADEMIYA_AI_API_KEY=','AICADEMIYA_WEB_SEARCH_ENABLED=false','AICADEMIYA_DOCUMENT_WORKER_COMMAND=',str(TARGET/'.venv/bin/python'),'-B','-c',code]
 smoke=subprocess.check_output(cmd,text=True);assert 'staged_actual_uid_app_boot_ok'in smoke
 assert CURRENT.resolve()==old
 report={'status':'staged_not_promoted','release':str(TARGET),'source_file_count':len(manifest['files']),'requirements_identical':True,'venv_version':copied['version'],'copied_site_bytes':size,'package_versions_unchanged':True,'package_count':len(copied['packages']),'no_external_site_links':True,'pip_check':check.strip(),'actual_uid999_app_boot':True,'production_link_unchanged':True,'old_release':str(old)}
 OUT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
