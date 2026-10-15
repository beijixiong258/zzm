"""Actual Linux UDS/CPU subprocess tests; synthetic lease owner, no GPU calls."""
from pathlib import Path
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/document_stage12'), str(ROOT/'tools/material_stage13')]
from gpu_lease import DocumentLease, LeaseError, LeaseTransportError, LeaseCancelled, T10B
from prepared_material import visual_plan


class FakeOwner:
    """Real abstract Unix socket; every allocation/generation result is synthetic."""
    def __init__(self, transform=None):
        self.path = '\0aicademiya-stage14-'+uuid.uuid4().hex
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(self.path); self.socket.listen(); self.socket.settimeout(.1)
        self.token = 'synthetic_capability_'+uuid.uuid4().hex
        self.frames = []; self.transform = transform
        self.done = threading.Event(); self.handled = threading.Event()
        self.thread = threading.Thread(target=self.serve, daemon=True); self.thread.start()

    def serve(self):
        while not self.done.is_set():
            try:peer, _ = self.socket.accept()
            except socket.timeout:continue
            except OSError:return
            with peer:
                peer.settimeout(2);data=b''
                try:
                    while not data.endswith(b'\n'):
                        chunk=peer.recv(4096)
                        if not chunk:raise OSError('test peer closed')
                        data+=chunk
                    frame=json.loads(data);self.frames.append(frame);self.handled.set()
                    op=frame['op']
                    if op=='reserve':
                        result={'lease_token':self.token,'epoch':1,'gpu_uuid':T10B,'worker':'t10b',
                                'expires_at':time.time()+120,'heartbeat_interval_seconds':.05}
                    elif op=='heartbeat':result={'phase':'leased','return_due':False,'expires_at':time.time()+120}
                    else:result={'phase':'teaching'}
                    reply={'ok':True,'result':result}
                    if self.transform:reply=self.transform(frame,reply)
                    if reply is not None:
                        raw=reply if isinstance(reply,bytes)else json.dumps(reply).encode()+b'\n'
                        peer.sendall(raw)
                except (OSError,ValueError):pass

    def client(self, stop=None, **kwargs):
        c=DocumentLease('/synthetic-abstract-test', 'synthetic-job', stop or threading.Event(),
                        expected_uid=os.geteuid(), control_timeout=.5,reserve_timeout=.5,**kwargs)
        # Test transport only: production still requires an absolute filesystem path.
        c.path=self.path
        return c

    def close(self):
        self.done.set();self.socket.close();self.thread.join(3)
        assert not self.thread.is_alive()


class LeaseTests(unittest.TestCase):
    def setUp(self):self.owner=None;self.client=None
    def tearDown(self):
        if self.client:
            self.client._done.set()
            if self.client._thread:self.client._thread.join(2)
        if self.owner:self.owner.close()
    def make(self, transform=None):
        self.owner=FakeOwner(transform);self.client=self.owner.client();return self.client
    def test_real_peer_credentials_and_immediate_heartbeat(self):
        c=self.make();self.assertEqual(c.reserve(),T10B)
        self.assertEqual([f['op']for f in self.owner.frames[:2]],['reserve','heartbeat'])
        c.check();self.assertEqual(c.release()['phase'],'teaching')
        self.assertNotIn(self.owner.token,json.dumps(c.evidence()))
    def test_ambiguous_reserve_retry_same_id(self):
        count=0
        def reply(frame,value):
            nonlocal count
            if frame['op']=='reserve':
                count+=1
                if count==1:return None
            return value
        c=self.make(reply);c.reserve();c.release()
        rows=[f for f in self.owner.frames if f['op']=='reserve']
        self.assertEqual(len(rows),2);self.assertEqual(rows[0],rows[1])
    def test_rejection_is_not_retried(self):
        c=self.make(lambda f,v:{'ok':False,'error':'not printed '+self.owner.token})
        with self.assertRaisesRegex(LeaseError,'request rejected')as error:c.reserve()
        self.assertEqual(len(self.owner.frames),1);self.assertNotIn(self.owner.token,str(error.exception))
    def test_foreign_owner_uid_denied(self):
        c=self.make();c.expected_uid=os.geteuid()+1
        with self.assertRaisesRegex(LeaseError,'Unexpected local'):c.reserve()
    def test_wrong_gpu_grant_never_usable(self):
        def reply(f,v):
            if f['op']=='reserve':v['result']['gpu_uuid']='GPU-469d42c9-519f-c217-6ad4-19ab92321d12'
            return v
        c=self.make(reply)
        with self.assertRaisesRegex(LeaseError,'fixed worker'):c.reserve()
        with self.assertRaises(LeaseError):c.check()
    def test_immediate_return_request_blocks_start(self):
        def reply(f,v):
            if f['op']=='heartbeat':v['result'].update(phase='return_requested',return_due=True)
            return v
        c=self.make(reply)
        with self.assertRaisesRegex(LeaseError,'must be returned'):c.reserve()
        self.assertEqual(c.release()['phase'],'teaching')
    def test_heartbeat_loss_signals_owned_job_stop(self):
        count=0
        def reply(f,v):
            nonlocal count
            if f['op']=='heartbeat':
                count+=1
                if count>1:return {'ok':False,'error':'synthetic expiry'}
            return v
        c=self.make(reply);c.reserve()
        self.assertTrue(c.stop.wait(3))
        with self.assertRaises(LeaseError):c.check()
        self.assertEqual(c.release()['phase'],'teaching')
    def test_cancellation_before_reserve_no_request(self):
        c=self.make();c.stop.set()
        with self.assertRaises(LeaseCancelled):c.reserve()
        self.assertEqual(self.owner.frames,[])
    def test_cancelled_unknown_reply_never_grants(self):
        def reply(f,v):
            if f['op']=='reserve':self.client.stop.set();return None
            return v
        c=self.make(reply)
        with self.assertRaises(LeaseError):c.reserve()
        self.assertIsNone(c.gpu_uuid);self.assertEqual(len(self.owner.frames),1)
    def test_oversized_reply_no_retry(self):
        c=self.make(lambda f,v:b'x'*17000+b'\n')
        with self.assertRaisesRegex(LeaseError,'exceeds'):c.reserve()
        self.assertEqual(len(self.owner.frames),1)
    def test_expired_grant_rejected(self):
        def reply(f,v):
            v['result']['expires_at']=time.time()-1;return v
        c=self.make(reply)
        with self.assertRaisesRegex(LeaseError,'fixed worker'):c.reserve()
    def test_release_pending_is_not_teaching_ready(self):
        def reply(f,v):
            if f['op']=='release':v['result']['phase']='return_requested'
            return v
        c=self.make(reply);c.reserve();result=c.release()
        self.assertTrue(result['acknowledged']);self.assertFalse(result['teaching_ready'])
    def test_lost_release_reply_retries_same_capability(self):
        count=0
        def reply(f,v):
            nonlocal count
            if f['op']=='release':
                count+=1
                if count==1:return None
            return v
        c=self.make(reply);c.reserve();c.release()
        rows=[f for f in self.owner.frames if f['op']=='release'];self.assertEqual(len(rows),2);self.assertEqual(rows[0],rows[1])
    def test_explicit_cooldown_wait_retries_same_job(self):
        count=0
        def reply(f,v):
            nonlocal count
            if f['op']=='reserve':
                count+=1
                if count==1:return {'ok':False,'retryable':True,'code':'teaching_cooldown','phase':'teaching','retry_after_seconds':.03}
            return v
        c=self.make(reply);c.reserve();c.release()
        reserves=[x for x in self.owner.frames if x['op']=='reserve'];self.assertEqual(len(reserves),2);self.assertEqual(reserves[0],reserves[1])
    def test_wait_has_document_deadline(self):
        c=self.make(lambda f,v:{'ok':False,'retryable':True,'code':'resource_wait','phase':'return_requested','retry_after_seconds':.05})
        c.reserve_timeout=.12
        with self.assertRaisesRegex(LeaseTransportError,'deadline'):c.reserve()
        self.assertIsNone(c.gpu_uuid)
    def test_blocked_is_not_retryable_even_if_malformed_metadata_says_so(self):
        c=self.make(lambda f,v:{'ok':False,'retryable':True,'code':'resource_wait','phase':'blocked','retry_after_seconds':.05})
        with self.assertRaisesRegex(LeaseError,'rejected'):c.reserve()
        self.assertEqual(len(self.owner.frames),1)
    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):DocumentLease('relative','job',threading.Event())
        with self.assertRaises(ValueError):DocumentLease('/sock','file/path',threading.Event())
        with self.assertRaises(ValueError):DocumentLease('/sock','job',threading.Event(),expected_gpu='v100')


class PortLifecycleTests(unittest.TestCase):
    def test_live_listener_still_blocks_model_port(self):
        from document_worker_service import ensure_model_port_available
        with socket.socket()as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',0));server.listen()
            with self.assertRaises(OSError):ensure_model_port_available(server.getsockname()[1])
    def test_closed_server_time_wait_is_not_a_live_model(self):
        from document_worker_service import ensure_model_port_available
        server=socket.socket();server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);server.bind(('127.0.0.1',0));server.listen();port=server.getsockname()[1]
        client=socket.create_connection(('127.0.0.1',port));accepted,_=server.accept()
        accepted.sendall(b'x');accepted.shutdown(socket.SHUT_WR)
        self.assertEqual(client.recv(1),b'x');self.assertEqual(client.recv(1),b'');client.close();accepted.close();server.close()
        with socket.socket()as legacy_probe:
            with self.assertRaises(OSError):legacy_probe.bind(('127.0.0.1',port))
        ensure_model_port_available(port)


class CPUPhaseTests(unittest.TestCase):
    def setUp(self):
        import document_worker_service as service
        self.service=service
        self.tmp=tempfile.TemporaryDirectory(prefix='s14-cpu-',dir=os.environ['TMPDIR'])
        self.root=Path(self.tmp.name);service.STOP.clear()
        self.patches=[patch.object(service,'HOME',self.root/'home'),
                      patch.object(service,'cpu_prefix',return_value=(0,[])),
                      patch.object(service,'runtime_python',return_value=Path(sys.executable)),
                      patch.object(service,'available_mib',return_value=12000)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.service.STOP.clear();self.tmp.cleanup()
    def source(self,kind='text'):
        import pymupdf as fitz
        from PIL import Image
        p=self.root/(kind+'.pdf');d=fitz.open();page=d.new_page()
        if kind!='blank':page.insert_text((40,50),'This is a sufficiently long native text paragraph for CPU-only source processing.')
        if kind=='image':
            buf=io.BytesIO();Image.new('RGB',(32,32),(20,120,70)).save(buf,format='PNG');page.insert_image(fitz.Rect(50,70,150,170),stream=buf.getvalue())
        if kind=='vector':page.draw_rect(fitz.Rect(40,70,150,150),color=(1,0,0))
        d.save(p);d.close();return p
    def test_actual_native_pdf_never_touches_gpu(self):
        src=self.source();out=self.root/'out'
        with patch.object(self.service,'DocumentLease',side_effect=AssertionError('must not lease')),patch.object(self.service,'gpu_free_mib',side_effect=AssertionError('must not query GPU')):
            result=self.service.run_job(src,out,30)
        self.assertEqual(result['status'],'complete');self.assertEqual(result['execution_kind'],'native_only')
        self.assertFalse(result['gpu_lease_used']);self.assertFalse(result['fresh_inference'])
        self.assertEqual(json.loads((out/'manifest.json').read_text())['page_count'],1)
    def test_blank_pdf_no_lease(self):
        with patch.object(self.service,'DocumentLease',side_effect=AssertionError('must not lease')):
            result=self.service.run_job(self.source('blank'),self.root/'out',30)
        self.assertFalse(result['visual_plan']['needs_gpu'])
    def test_image_pdf_prepared_before_missing_lease_rejection(self):
        out=self.root/'out'
        with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':T10B,'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':''}),patch.object(self.service,'DocumentLease',side_effect=AssertionError('no configured lease')):
            with self.assertRaisesRegex(LeaseError,'exclusive GPU lease'):self.service.run_job(self.source('image'),out,30)
        report=json.loads((out/'raw/supervisor.json').read_text())
        self.assertEqual(report['visual_plan']['visual_pages'],[1]);self.assertFalse(report['gpu_lease_used'])
        self.assertTrue((out/'raw/native-preparation-receipt.json').is_file());self.assertTrue(report['owned_processes_closed'])
    def test_vector_pdf_not_mislabelled_native_complete(self):
        out=self.root/'out'
        with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':T10B,'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':''}):
            with self.assertRaises(LeaseError):self.service.run_job(self.source('vector'),out,30)
        report=json.loads((out/'raw/supervisor.json').read_text());self.assertEqual(report['visual_plan']['fullpage_pages'],[1])
    def test_original_unchanged(self):
        src=self.source();original=src.read_bytes();self.service.run_job(src,self.root/'out',30);self.assertEqual(src.read_bytes(),original)
    def test_existing_output_refused(self):
        out=self.root/'out';out.mkdir();(out/'sentinel').write_text('keep')
        with self.assertRaisesRegex(ValueError,'fresh'):self.service.run_job(self.source(),out,30)
        self.assertEqual((out/'sentinel').read_text(),'keep')

    def test_actual_failed_model_child_closed_before_release(self):
        service=self.service;events=[];children=[];test=self
        real_popen=service.subprocess.Popen
        class SyntheticLease:
            gpu_uuid=T10B
            def __init__(self,*args,**kwargs):events.append('lease_created')
            def reserve(self):
                receipts=list((test.root/'home/jobs').glob('*/native/receipt.json'))
                test.assertEqual(len(receipts),1)
                test.assertEqual(json.loads(receipts[0].read_text())['status'],'complete')
                events.append('reserved');return T10B
            def check(self):pass
            def evidence(self):return {'phase':'teaching','synthetic':True}
            def release(self):
                test.assertTrue(children and all(p.poll() is not None for p in children))
                events.append('released');return {'phase':'teaching','acknowledged':True,'synthetic':True}
        def spawn(command,**kwargs):
            if '--alias' in command:
                test.assertIn('reserved',events);test.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'],T10B)
                events.append('model_started')
                child=real_popen([sys.executable,'-c','raise SystemExit(7)'],**kwargs);children.append(child);return child
            test.assertNotIn('reserved',events)
            return real_popen(command,**kwargs)
        out=self.root/'out'
        with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':T10B,'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':'/synthetic-control'}),patch.object(service,'DocumentLease',SyntheticLease),patch.object(service.subprocess,'Popen',side_effect=spawn),patch.object(service,'gpu_free_mib',return_value=16000):
            with self.assertRaisesRegex(RuntimeError,'failed to start'):
                service.run_job(self.source('image'),out,30)
        self.assertEqual(events,['lease_created','reserved','model_started','released'])
        result=json.loads((out/'raw/supervisor.json').read_text())
        self.assertEqual(result['status'],'failed');self.assertTrue(result['owned_processes_closed'])
        self.assertTrue(result['gpu_return']['acknowledged'])
    def test_lease_denial_starts_no_model(self):
        service=self.service;events=[]
        class DeniedLease:
            gpu_uuid=None
            def __init__(self,*args,**kwargs):pass
            def reserve(self):events.append('denied');raise LeaseError('synthetic lease denied')
            def release(self):events.append('cleanup');return {'acknowledged':False,'phase':'not_granted'}
            def evidence(self):return {'phase':'not_granted','synthetic':True}
        out=self.root/'out'
        with patch.dict(os.environ,{'AICADEMIYA_DOCUMENT_GPU_UUID':T10B,'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET':'/synthetic-control'}),patch.object(service,'DocumentLease',DeniedLease),patch.object(service,'gpu_free_mib',side_effect=AssertionError('no GPU activity without lease')):
            with self.assertRaisesRegex(LeaseError,'denied'):service.run_job(self.source('image'),out,30)
        report=json.loads((out/'raw/supervisor.json').read_text())
        self.assertNotIn('model_pid',report);self.assertEqual(events,['denied','cleanup'])


if __name__=='__main__':unittest.main()
