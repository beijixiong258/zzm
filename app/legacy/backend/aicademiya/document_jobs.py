"""One durable serial worker, owned child lifetime, no automatic failed-job retry."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import threading
import time

from .document_bundle import BundleError, FULL_FORMATS, MAX_MANIFEST_BYTES, validate_bundle, validate_manifest
from .document_storage import check_job_target, fail_job, install_document
from .db import now

FAILED = 'Document processing failed; the original and any previous valid document are retained'
INTERRUPTED = 'Document processing was interrupted; explicitly retry when ready'
STALE = 'Document processing could not commit because source, revision or staff access changed'


def configured_command(value=None):
    if value is None:
        raw = os.getenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', '')
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(v, str) and v and '\0' not in v for v in value):
        return None
    return tuple(value)


class DocumentQueue:
    def __init__(self, db, uploads, *, command=None, processor=None, timeout=None):
        self.db, self.uploads = db, Path(uploads)
        self.command = configured_command(command)
        self.processor = processor  # Explicit isolated test/embedding injection, never a fake fallback.
        formats = os.getenv('AICADEMIYA_DOCUMENT_FORMATS', 'pdf').split(',')
        self.formats = tuple(dict.fromkeys(x.strip().lower() for x in formats if x.strip()))
        if not self.formats or any(x not in FULL_FORMATS for x in self.formats):
            self.command, self.processor, self.formats = None, None, ()
        try:
            self.timeout = float(timeout if timeout is not None else os.getenv('AICADEMIYA_DOCUMENT_WORKER_TIMEOUT', '3600'))
            if not 1 <= self.timeout <= 86400:
                raise ValueError()
        except (ValueError, TypeError):
            self.command, self.processor, self.timeout = None, None, 3600
        self.stop_event, self.wakeup = threading.Event(), threading.Event()
        self.thread, self.child = None, None
        self.child_lock = threading.Lock()
        self.lifecycle_lock = threading.Lock()
        self.lifespans = 0

    @property
    def available(self):
        return bool(self.command or self.processor)

    def start(self):
        with self.lifecycle_lock:
            self.lifespans += 1
            if self.lifespans > 1:
                return
        # The application deployment is explicitly one-worker. Recovery runs only
        # once per lifespan, not per request or database migration.
        with self.db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for job in conn.execute("SELECT * FROM document_jobs WHERE status='running'").fetchall():
                fail_job(conn, job, INTERRUPTED)
        self.stop_event.clear()
        if self.available:
            self.thread = threading.Thread(target=self.run, name='aicademiya-document-worker', daemon=True)
            self.thread.start()

    def notify(self):
        self.wakeup.set()

    def terminate_child(self):
        with self.child_lock:
            child = self.child
            if not child or child.poll() is not None:
                return
            if os.name == 'nt':
                # Venv launchers can spawn a second Python process. Kill ONLY the
                # exact worker-owned process tree, not other Python/services.
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=15)

    def close(self):
        with self.lifecycle_lock:
            if not self.lifespans:
                return
            self.lifespans -= 1
            if self.lifespans:
                return
        self.stop_event.set()
        self.wakeup.set()
        self.terminate_child()
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                raise RuntimeError('Injected document processor did not honor shutdown cancellation')
            self.thread = None

    def claim(self):
        with self.db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job = conn.execute("SELECT * FROM document_jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if not job:
                return None
            try:
                check_job_target(conn, job)
            except Exception:
                fail_job(conn, job, STALE)
                return False
            conn.execute("UPDATE document_jobs SET status='running',started_at=? WHERE id=? AND status='queued'", (now(), job['id']))
            return dict(conn.execute('SELECT * FROM document_jobs WHERE id=?', (job['id'],)).fetchone())

    def execute(self, source, root):
        if self.processor:
            self.processor(source, root, self.stop_event)
            return
        command = [*self.command, '--input', str(source), '--output', str(root)]
        # Output/receipt stays in the parser bundle. Do not retain unlimited
        # stdout/stderr or expose argv/errors. No shell interpolation at any point.
        with self.child_lock:
            if self.stop_event.is_set():
                raise RuntimeError('Cancelled')
            self.child = subprocess.Popen(command, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=os.name != 'nt')
            child = self.child
        deadline = time.monotonic() + self.timeout
        try:
            while child.poll() is None:
                if self.stop_event.wait(.1) or time.monotonic() >= deadline:
                    self.terminate_child()
                    raise RuntimeError('Worker interrupted or exceeded its timeout')
            if child.returncode:
                raise RuntimeError('Worker failed')
        finally:
            if child.poll() is None:
                self.terminate_child()
            with self.child_lock:
                self.child = None

    def run_job(self, job):
        root = self.uploads / 'documents' / job['id']
        try:
            # Fresh output is never reused, even for interrupted/failed jobs.
            root.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if root.exists() or root.is_symlink() or root.parent.is_symlink():
                raise RuntimeError('Output is not fresh')
            # The worker creates its fresh output directory; a private owning
            # parent prevents local users traversing output during processing.
            os.chmod(root.parent, 0o700)
            with self.db.connect() as conn:
                row = check_job_target(conn, job)
                source = Path(row['file_path'])
            if not self.recover_transferred_result(job, root):
                self.execute(source, root)
            manifest = validate_bundle(root, job['source_sha256'], job['page_count'])
            if (manifest.get('source_format') or 'pdf') != source.suffix.lower().lstrip('.'):
                raise BundleError('Worker document format does not match the original source')
            if source.suffix.lower() in ('.txt', '.md'):
                from tools.material_stage13.source_text import decode_text
                literal, _ = decode_text(source.read_bytes())
                supplied = ''.join(b['text'] for page in manifest['pages'] for b in page['blocks'])
                if supplied != literal:
                    raise BundleError('Complete text must preserve every decoded original character')
            if source.suffix.lower() in ('.pptx','.ppt','.docx','.doc','.xls','.xlsx'):
                from .document_supplements import index_supplements
                manifest['supplements']=index_supplements(source,root,manifest)
                manifest=validate_manifest(manifest,source_sha256=job['source_sha256'],page_count=manifest['page_count'])
                if len(json.dumps(manifest,ensure_ascii=False).encode('utf-8'))>MAX_MANIFEST_BYTES:
                    raise BundleError('Complete source and supplementary text exceed manifest bounds')
            if self.stop_event.is_set():
                raise RuntimeError('Cancelled')
            with self.db.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('SAVEPOINT document_install')
                try:
                    install_document(conn, job, manifest, root)
                except Exception:
                    conn.execute('ROLLBACK TO document_install')
                    fail_job(conn, job, STALE)
                finally:
                    conn.execute('RELEASE document_install')
        except Exception:
            with self.db.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                fail_job(conn, job, INTERRUPTED if self.stop_event.is_set() else FAILED)
        # Raw/partial output intentionally retained; no stage12 auto-cleanup.

    def recover_transferred_result(self, job, root):
        """Explicit retry of the observed post-parse SSH shutdown failure only.

        Never mark the failed attempt successful or trust partial/mismatched
        output. The ordinary new-job actor/source/revision guards still apply.
        """
        with self.db.connect() as conn:
            candidates = conn.execute("""SELECT id FROM document_jobs WHERE material_id=?
                AND source_sha256=? AND expected_revision IS ? AND status='failed' AND error=?
                ORDER BY created_at DESC,rowid DESC""", (job['material_id'], job['source_sha256'],
                job['expected_revision'], FAILED)).fetchall()
        for previous in candidates:
            old = self.uploads / 'documents' / previous['id']
            try:
                paths = [old/'raw/ssh-job.json', old/'raw/supervisor.json', old/'receipt.json']
                if any(not p.is_file() or p.is_symlink() or p.stat().st_size > 65536 for p in paths):
                    continue
                transfer, supervisor, receipt = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
                if (transfer.get('returncode') in (None, 0) or not transfer.get('bytes_received')
                    or supervisor.get('status') != 'complete' or not supervisor.get('owned_processes_closed')
                    or receipt.get('status') != 'complete'):
                    continue
                validate_bundle(old, job['source_sha256'], job['page_count'])
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if self.stop_event.is_set():
                raise RuntimeError('Cancelled before verified result recovery')
            shutil.copytree(old, root)
            (root/'raw/recovery.json').write_text(json.dumps({
                'source_job_id': previous['id'], 'retry_job_id': job['id'],
                'source_sha256': job['source_sha256'], 'model_rerun': False,
                'reason': 'Recovered a fully validated extraction already received before an SSH process shutdown failure.'
            }, indent=2) + '\n', encoding='utf-8')
            return True
        return False

    def run(self):
        while not self.stop_event.is_set():
            job = self.claim()
            if job:
                self.run_job(job)
            elif job is False:
                continue
            else:
                self.wakeup.wait(.5)
                self.wakeup.clear()
