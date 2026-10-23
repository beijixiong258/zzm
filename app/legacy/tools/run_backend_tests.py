"""Run project pytest with a unique retained temp root (never the user's data)."""
from pathlib import Path
import os
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]

def main():
    home=os.getenv('HERMES_HOME')
    scratch=Path(home)/'cache'/'scratch' if home else ROOT/'artifacts'/'qa-temp'
    scratch.mkdir(parents=True,exist_ok=True)
    temp=scratch/('aicademiya-pytest-'+uuid.uuid4().hex)
    env=os.environ.copy()
    env.update(TMPDIR=str(scratch),TEMP=str(scratch),TMP=str(scratch))
    args=sys.argv[1:] or ['backend/tests','-q']
    if any(a.startswith('--basetemp') for a in args):raise SystemExit('This runner owns its unique --basetemp directory.')
    print('Retained test temporary files: '+str(temp),flush=True)
    return subprocess.run([sys.executable,'-m','pytest','-p','no:cacheprovider','--basetemp',str(temp),*args],cwd=ROOT,env=env).returncode

if __name__=='__main__':raise SystemExit(main())
