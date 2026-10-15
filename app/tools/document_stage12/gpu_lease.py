"""Document-side fixed T10-B lease client. Capabilities never leave memory.

One JSON-line request per private Unix connection. A lost reserve reply is
retried once with the SAME job identity; a cancelled/uncertain reserve never
starts a model. The owner alone proves an empty GPU and teaching rejoin.
"""
from __future__ import annotations
import json
import math
import os
import re
import select
import socket
import struct
import threading
import time

T10B = 'GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'


class LeaseError(RuntimeError):
    pass


class LeaseTransportError(LeaseError):
    pass


class LeaseCancelled(LeaseError):
    pass

class LeaseWaiting(LeaseError):
    def __init__(self, phase, seconds):
        super().__init__('GPU resource is busy; waiting within the document deadline')
        self.phase, self.seconds = phase, seconds


class DocumentLease:
    def __init__(self, path, job_id, stop, *, expected_uid=1000,
                 expected_gpu=T10B, reserve_timeout=855, control_timeout=8):
        if not isinstance(path, str) or not path.startswith('/') or '\0' in path:
            raise ValueError('An absolute private Unix socket path is required')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', job_id):
            raise ValueError('An opaque document job identity is required')
        if expected_gpu != T10B or type(expected_uid) is not int or expected_uid < 0:
            raise ValueError('Fixed document GPU and owner UID required')
        self.path, self.job_id, self.stop = path, job_id, stop
        self.expected_uid, self.expected_gpu = expected_uid, expected_gpu
        self.reserve_timeout, self.control_timeout = reserve_timeout, control_timeout
        self._token = None
        self._done = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._failure = None
        self.expires_at = 0
        self.gpu_uuid = None
        self.epoch = None
        self.phase = 'not_reserved'
        self.interval = 0

    def _request(self, payload, timeout, *, cancellable=True):
        frame = json.dumps(payload, separators=(',', ':')).encode() + b'\n'
        if len(frame) > 4096:
            raise LeaseError('Lease request exceeds protocol bound')
        deadline = time.monotonic() + timeout
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(min(3, timeout))
                peer.connect(self.path)
                if not hasattr(socket, 'SO_PEERCRED'):
                    raise LeaseError('Linux local owner credentials required')
                _pid, uid, _gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != self.expected_uid:
                    raise LeaseError('Unexpected local GPU resource owner')
                peer.sendall(frame)
                data = bytearray()
                while True:
                    if cancellable and self.stop.is_set():
                        raise LeaseCancelled('Document cancelled while waiting for GPU resources')
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise LeaseTransportError('GPU resource reply timed out')
                    if not select.select([peer], [], [], min(.2, remaining))[0]:
                        continue
                    chunk = peer.recv(4096)
                    if not chunk:
                        raise LeaseTransportError('GPU resource reply was interrupted')
                    data.extend(chunk)
                    if len(data) > 16384:
                        raise LeaseError('GPU resource reply exceeds protocol bound')
                    if b'\n' in data:
                        line, extra = data.split(b'\n', 1)
                        if extra.strip():
                            raise LeaseError('Unexpected extra GPU resource reply')
                        try:
                            reply = json.loads(line)
                        except (ValueError, UnicodeError):
                            raise LeaseError('Invalid GPU resource reply') from None
                        if isinstance(reply, dict) and reply.get('ok') is False and reply.get('retryable') is True:
                            delay=reply.get('retry_after_seconds')
                            phase=reply.get('phase')
                            if (reply.get('code') in ('resource_wait','teaching_cooldown')
                                    and phase in ('teaching','leased','draining','releasing','return_requested','loading')
                                    and not isinstance(delay,bool) and isinstance(delay,(int,float))
                                    and math.isfinite(delay) and 0 < delay <= 900):
                                raise LeaseWaiting(phase,delay)
                        if not isinstance(reply, dict) or reply.get('ok') is not True:
                            # Do not embed arbitrary server text or runtime capability.
                            raise LeaseError('GPU resource request rejected; inspect owner status')
                        if not isinstance(reply.get('result'), dict):
                            raise LeaseError('Invalid GPU resource result')
                        return reply['result']
        except (OSError, TimeoutError):
            raise LeaseTransportError('GPU resource owner unavailable') from None

    def reserve(self):
        if self._token is not None:
            raise LeaseError('This client already holds a GPU capability')
        if self.stop.is_set():
            raise LeaseCancelled('Document cancelled before GPU reserve')
        self.phase = 'reserving'
        payload = {'op':'reserve', 'job_id':self.job_id, 'worker':'t10b', 'needs_gpu':True}
        deadline=time.monotonic()+self.reserve_timeout
        transport_retries=0
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise LeaseTransportError('Document deadline reached while waiting for GPU resources')
            try:
                grant = self._request(payload, remaining)
                break
            except LeaseWaiting as wait:
                self.phase='waiting_'+wait.phase
                if self.stop.wait(min(wait.seconds,5,max(0,deadline-time.monotonic()))):
                    raise LeaseCancelled('Document cancelled while waiting for GPU resources')from None
            except LeaseTransportError:
                self.phase = 'reserve_reply_unknown'
                if transport_retries or self.stop.is_set():
                    raise
                transport_retries+=1
        token = grant.get('lease_token')
        expiry, interval = grant.get('expires_at'), grant.get('heartbeat_interval_seconds')
        if (not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', token)
                or grant.get('gpu_uuid') != self.expected_gpu or grant.get('worker') != 't10b'
                or type(grant.get('epoch')) is not int or grant['epoch'] < 1
                or isinstance(expiry, bool) or not isinstance(expiry, (int,float)) or not math.isfinite(expiry)
                or not time.time() < expiry <= time.time()+301
                or isinstance(interval, bool) or not isinstance(interval, (int,float)) or not math.isfinite(interval)
                or not 0 < interval <= 30):
            self.phase = 'invalid_grant'
            raise LeaseError('GPU grant does not match the fixed worker contract')
        self._token, self.expires_at, self.interval = token, expiry, interval
        self.epoch, self.gpu_uuid, self.phase = grant['epoch'], grant['gpu_uuid'], 'leased'
        # Revalidate immediately, before the caller may start CUDA.
        self.heartbeat()
        self._thread = threading.Thread(target=self._watch, name='document-gpu-lease', daemon=True)
        self._thread.start()
        return self.gpu_uuid

    def heartbeat(self):
        with self._lock:
            result = self._request({'op':'heartbeat', 'lease_token':self._token, 'active':True}, self.control_timeout)
            expiry = result.get('expires_at')
            if (result.get('phase') != 'leased' or result.get('return_due') is not False
                    or isinstance(expiry, bool) or not isinstance(expiry, (int,float))
                    or not math.isfinite(expiry) or not time.time() < expiry <= time.time()+301):
                self.phase = 'return_requested'
                raise LeaseError('Document GPU lease must be returned')
            self.expires_at = expiry

    def _watch(self):
        while not self._done.wait(self.interval):
            if self.stop.is_set():
                return
            try:
                self.heartbeat()
            except LeaseError as error:
                self._failure = str(error)
                self.phase = 'lease_lost'
                self.stop.set()
                return

    def check(self):
        if self._failure:
            raise LeaseError(self._failure)
        if self._token is None or time.time() >= self.expires_at:
            raise LeaseError('Document GPU lease is absent or expired')
        if self.stop.is_set():
            raise LeaseCancelled('Document GPU work cancelled')

    def release(self):
        """Call ONLY after the caller has stopped all of its GPU processes."""
        self._done.set()
        if self._thread:
            self._thread.join(timeout=self.control_timeout+2)
            if self._thread.is_alive():
                raise LeaseError('Lease heartbeat did not stop')
        if self._token is None:
            return {'phase':self.phase, 'acknowledged':False}
        with self._lock:
            payload = {'op':'release', 'lease_token':self._token}
            for attempt in range(2):
                try:
                    result = self._request(payload, 615, cancellable=False)
                    break
                except LeaseTransportError:
                    if attempt:
                        raise
            self.phase = result.get('phase', 'unknown')
            if self.phase not in ('teaching','return_requested','blocked'):
                raise LeaseError('Unrecognized GPU return state')
            return {'phase':self.phase, 'acknowledged':True,
                    'teaching_ready':self.phase == 'teaching'}

    def evidence(self):
        return {'phase':self.phase, 'worker':'t10b', 'gpu_uuid':self.gpu_uuid,
                'epoch':self.epoch, 'capability_persisted':False}
