"""Linux-only stdlib tests for explicit CPU/CUDA runtime selection."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import document_worker_service as service

GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
class RuntimeTests(unittest.TestCase):
 def test_default_cpu_has_no_gpu_offload(self):
  with patch.dict(os.environ,{},clear=True):
   spec=service.runtime_spec()
  self.assertEqual(spec['device'],'cpu');self.assertEqual(spec['gpu_uuid'],'')
  self.assertIn('--no-mmproj-offload',spec['offload'])
  self.assertEqual(spec['offload'][spec['offload'].index('--device')+1],'none')
 def test_cuda_is_explicit_and_requires_selected_device(self):
  with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':GPU},clear=True):spec=service.runtime_spec()
  self.assertEqual(spec['device'],'cuda');self.assertEqual(spec['gpu_uuid'],GPU)
  self.assertEqual(spec['offload'],['-ngl','99','--device','CUDA0'])
  self.assertNotIn('--no-mmproj-offload',spec['offload'])
 def test_relocated_runtime_precedes_embedded_build_paths(self):
  with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':GPU,'AICADEMIYA_DOCUMENT_CUDA_RUNTIME':'/opt/test-cuda','AICADEMIYA_DOCUMENT_CUDA_LIBS':'/opt/test-libs'},clear=True):spec=service.runtime_spec()
  self.assertEqual(str(spec['exe']),'/opt/test-cuda/bin/llama-server')
  self.assertTrue(spec['libraries'].startswith('/opt/test-cuda/bin:/opt/test-libs:'))
 def test_invalid_gpu_is_not_silently_cpu(self):
  with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':'missing'},clear=True):
   with self.assertRaises(ValueError):service.runtime_spec()
 def test_free_memory_query_uses_fixed_argv(self):
  with patch.object(service.subprocess,'run')as run:
   run.return_value.stdout='2300\n';self.assertEqual(service.gpu_free_mib(GPU),2300)
   self.assertEqual(run.call_args.args[0][1],'--id='+GPU)
 def test_insufficient_gpu_memory_starts_no_model(self):
  import io,sys
  import pymupdf as fitz
  from PIL import Image
  with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])as name:
   root=Path(name);source=root/'input.pdf';out=root/'result'
   image=io.BytesIO();Image.new('RGB',(32,32),'blue').save(image,format='PNG')
   pdf=fitz.open();page=pdf.new_page();page.insert_image(fitz.Rect(30,30,130,130),stream=image.getvalue());pdf.save(source);pdf.close()
   class SyntheticLease:
    gpu_uuid=GPU
    def __init__(self,*args,**kwargs):pass
    def reserve(self):return GPU
    def check(self):pass
    def release(self):return {'phase':'teaching','acknowledged':True,'synthetic':True}
    def evidence(self):return {'phase':'teaching','synthetic':True}
   real_spawn=service.subprocess.Popen;commands=[]
   def spawn(command,**kwargs):
    commands.append(command)
    if '--alias' in command:raise AssertionError('GPU model must not start below reserve')
    return real_spawn(command,**kwargs)
   with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':GPU,'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':'/synthetic'}),patch.object(service,'HOME',root/'home'),patch.object(service,'available_mib',return_value=12000),patch.object(service,'cpu_prefix',return_value=(0,[])),patch.object(service,'runtime_python',return_value=Path(sys.executable)),patch.object(service,'DocumentLease',SyntheticLease),patch.object(service,'gpu_free_mib',return_value=2000),patch.object(service.subprocess,'Popen',side_effect=spawn):
    service.STOP.clear()
    with self.assertRaisesRegex(MemoryError,'No CPU fallback'):service.run_job(source,out)
   self.assertEqual(len(commands),1);self.assertIn('native',commands[0])
   receipt=json.loads((out/'raw/supervisor.json').read_text())
   self.assertEqual(receipt['status'],'failed');self.assertEqual(receipt['device'],'cuda')
   self.assertTrue(receipt['owned_processes_closed']);self.assertFalse(receipt['fresh_inference'])
   self.assertTrue(receipt['gpu_return']['acknowledged'])
if __name__=='__main__':unittest.main()
