"""Linux CPU-only fixed-profile and supervisor tests. ALL leases/model replies
and page-worker results below are synthetic; no GPU driver/model call occurs.
"""
from pathlib import Path
import hashlib,io,json,os,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage14')]
import document_worker_service as service
from page_vision_runtime import fixed_vision_profile
import test_worker_lease as legacy_tests
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'

def profile():
 cmd=['/root-owned/bin/llama-server','-m','/root-owned/model.gguf','--mmproj','/root-owned/mmproj.gguf','--chat-template-file','/root-owned/template.jinja']
 for k,v in {'--host':'127.0.0.1','--port':'18893','--parallel':'1','--ctx-size':'8192','--kv-unified-per-slot':'8192','--alias':'aicademiya-materials','--spec-type':'none','--image-max-tokens':'3072','--cache-ram':'0'}.items():cmd.extend([k,v])
 return {'schema_version':1,'command':cmd,'environment':{'LD_LIBRARY_PATH':'/root-owned/lib','CUDA_DEVICE_ORDER':'PCI_BUS_ID'},'model_alias':'aicademiya-materials','context_size':8192}

class ProfileTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']);self.path=Path(self.tmp.name)/'profile.json'
 def tearDown(self):self.tmp.cleanup()
 def load(self,p,*,uid=0,writable=False,wrong_hash=False):
  raw=json.dumps(p).encode();self.path.write_bytes(raw);real=Path.lstat
  def metadata(path):
   st=real(path);return types.SimpleNamespace(st_uid=uid,st_mode=(st.st_mode & ~0o022)|(0o020 if writable else 0))
  with patch.object(Path,'lstat',metadata):return fixed_vision_profile(self.path,'0'*64 if wrong_hash else hashlib.sha256(raw).hexdigest())
 def test_fixed_profile_selected_without_GPU(self):
  spec=self.load(profile());self.assertTrue(spec['page_markdown']);self.assertEqual(spec['context_size'],8192);self.assertEqual(spec['command'],profile()['command'])
 def test_wrong_owner_rejected(self):
  with self.assertRaisesRegex(ValueError,'root-owned'):self.load(profile(),uid=1000)
 def test_group_writable_rejected(self):
  with self.assertRaisesRegex(ValueError,'root-owned'):self.load(profile(),writable=True)
 def test_hash_pin_required(self):
  with self.assertRaisesRegex(ValueError,'checksum'):self.load(profile(),wrong_hash=True)
 def test_public_bind_rejected(self):
  p=profile();p['command'][p['command'].index('--host')+1]='0.0.0.0'
  with self.assertRaisesRegex(ValueError,'--host'):self.load(p)
 def test_duplicate_flags_rejected(self):
  p=profile();p['command']+=['--ctx-size','65536']
  with self.assertRaisesRegex(ValueError,'duplicate'):self.load(p)
 def test_teaching_snapshot_path_rejected(self):
  p=profile();p['command']+=['--slot-save-path','/teaching/cache']
  with self.assertRaisesRegex(ValueError,'snapshots'):self.load(p)
 def test_gpu_mask_cannot_be_injected_by_profile(self):
  p=profile();p['environment']['CUDA_VISIBLE_DEVICES']='0'
  with self.assertRaisesRegex(ValueError,'environment'):self.load(p)
 def test_page_backend_requires_lease_gpu_configuration(self):
  with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_VISION_PROFILE':'/fixed/profile'},clear=True):
   with self.assertRaisesRegex(ValueError,'leased CUDA'):service.runtime_spec()

HTTP_SERVER="""from http.server import HTTPServer,BaseHTTPRequestHandler
import json
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({'status':'ok'}if self.path=='/health'else{'modalities':{'vision':True}}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
class S(HTTPServer):allow_reuse_address=True
S(('127.0.0.1',18893),H).serve_forever()
"""
PAGE_FIXTURE="""import json,shutil,sys
from pathlib import Path
src,out=map(Path,sys.argv[1:3]);shutil.copytree(src,out)
r={'status':'complete','synthetic_fixture':True,'model_calls':1,'visual_transcription_complete':True,'visual_failed_pages':[],'page_timings':[{'page':1,'model_processed':True,'model_calls':1}]}
(out/'receipt.json').write_text(json.dumps(r))
"""

class SupervisorTests(unittest.TestCase):
 setUp=legacy_tests.CPUPhaseTests.setUp;tearDown=legacy_tests.CPUPhaseTests.tearDown;source=legacy_tests.CPUPhaseTests.source
 def run_case(self,cancel=False):
  test=self;children=[];events=[];real_spawn=service.subprocess.Popen
  class Lease:
   gpu_uuid=GPU
   def __init__(self,*a,**k):pass
   def reserve(self):events.append('lease');return GPU
   def check(self):pass
   def evidence(self):return {'synthetic_fixture':True}
   def release(self):
    test.assertTrue(children and all(p.poll()is not None for p in children));events.append('released');return {'phase':'teaching','acknowledged':True,'synthetic_fixture':True}
  p=profile();spec={'device':'cuda','gpu_uuid':GPU,'page_markdown':True,'command':p['command'],'exe':Path(p['command'][0]),'environment':p['environment'],'libraries':p['environment']['LD_LIBRARY_PATH'],'model_alias':p['model_alias'],'context_size':8192}
  def spawn(cmd,**kw):
   if cmd==p['command']:
    test.assertEqual(events,['lease']);test.assertEqual(kw['env']['CUDA_VISIBLE_DEVICES'],GPU);events.append('model')
    child=real_spawn([sys.executable,'-u','-c',HTTP_SERVER],**kw);children.append(child);return child
   if any(str(x).endswith('page_worker.py')for x in cmd):
    test.assertIn('model',events);test.assertNotIn('--engine',cmd);test.assertEqual(kw['env']['CUDA_VISIBLE_DEVICES'],'');test.assertEqual(cmd[cmd.index('--pages')+1],'1');test.assertEqual(cmd[cmd.index('--ctx-size')+1],'8192');events.append('page-worker')
    if cancel:service.STOP.set()
    child=real_spawn([sys.executable,'-c',PAGE_FIXTURE,cmd[cmd.index('--prepared-dir')+1],cmd[cmd.index('--output')+1]],**kw);children.append(child);return child
   test.assertNotIn('lease',events);return real_spawn(cmd,**kw)
  out=self.root/'out'
  with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':'/synthetic'}),patch.object(service,'runtime_spec',return_value=spec),patch.object(service,'DocumentLease',Lease),patch.object(service.subprocess,'Popen',side_effect=spawn),patch.object(service,'gpu_free_mib',return_value=16000):
   if cancel:
    with self.assertRaisesRegex(RuntimeError,'cancelled'):service.run_job(self.source('image'),out,30)
    result=json.loads((out/'raw/supervisor.json').read_text());self.assertFalse(result['fresh_inference']);self.assertEqual(result['status'],'failed')
   else:
    result=service.run_job(self.source('image'),out,30);self.assertEqual(result['visual_backend'],'native+live-page-markdown');self.assertTrue(result['visual_transcription_complete']);self.assertEqual(result['model_processed_pages'],1)
  self.assertEqual(events,['lease','model','page-worker','released']);self.assertTrue(result['owned_processes_closed']);self.assertTrue(result['gpu_return']['acknowledged'])
 def test_cpu_fixture_leased_page_worker_and_cleanup(self):self.run_case()
 def test_cpu_fixture_cancel_closes_children_before_return(self):self.run_case(cancel=True)

if __name__=='__main__':unittest.main()
