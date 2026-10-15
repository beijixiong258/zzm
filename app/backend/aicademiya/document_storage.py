"""Immutable revisions and operational queue records. All mutations use a writer lock."""
import copy
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException

from .course_staff import AuthenticatedUser, live_actor
from .db import new_id, now
from .document_bundle import BundleError, FULL_FORMATS, source_identity, validate_manifest

JOB_FIELDS = ('id','material_id','status','created_at','started_at','finished_at','page_count','processed_pages','error','revision_id')
DOCUMENT_FIELDS = ('revision_id','source_sha256','page_count','block_count','quality','review_count','parser','created_at','warnings','source_format','has_rendered_pdf')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def migrate_documents(conn):
    conn.execute('SAVEPOINT stage12_documents')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS document_jobs (
            id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(id),
            request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
            requester_id TEXT NOT NULL, requester_role TEXT NOT NULL, token_hash TEXT,
            status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
            created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            page_count INTEGER, processed_pages INTEGER NOT NULL DEFAULT 0,
            error TEXT, revision_id TEXT, expected_revision TEXT,
            source_sha256 TEXT NOT NULL, source_path_hash TEXT NOT NULL,
            material_hash TEXT NOT NULL, UNIQUE(material_id,request_id))''')
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS document_one_active ON document_jobs(material_id) WHERE status IN ('queued','running')")
        conn.execute('''CREATE TABLE IF NOT EXISTS document_revisions (
            id TEXT PRIMARY KEY, material_id TEXT NOT NULL REFERENCES materials(id),
            source_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            parse_id TEXT NOT NULL, parent_revision TEXT, manifest_json TEXT NOT NULL,
            info_json TEXT NOT NULL, request_id TEXT, payload_hash TEXT,
            UNIQUE(material_id,request_id))''')
        conn.execute("CREATE TRIGGER IF NOT EXISTS immutable_document_update BEFORE UPDATE ON document_revisions BEGIN SELECT RAISE(ABORT,'Document revisions are immutable'); END")
        conn.execute("CREATE TRIGGER IF NOT EXISTS immutable_document_delete BEFORE DELETE ON document_revisions BEGIN SELECT RAISE(ABORT,'Document revisions are immutable'); END")
        conn.execute('PRAGMA user_version=9')
        conn.execute('RELEASE stage12_documents')
    except Exception:
        conn.execute('ROLLBACK TO stage12_documents')
        conn.execute('RELEASE stage12_documents')
        raise


def public_job(row):
    return {key: row[key] for key in JOB_FIELDS} if row else None


def public_document(value):
    if not value:
        return None
    result = {key: copy.deepcopy(value.get(key)) for key in DOCUMENT_FIELDS}
    parser = result.get('parser') or {}
    result['parser'] = {key: parser.get(key) for key in ('name', 'version', 'recipe')}
    return result


def revision_id(raw):
    return (raw.get('document') or {}).get('revision_id')


def get_document_manifest(conn, material_row):
    """Return (version-pinned manifest, internal Path), or (None, None).

    Caller MUST supply an already authorized current/snapshot row (resolve_material
    or material_rows from authorized session_access). Never looks up latest draft.
    Returned internal root MUST NOT enter a DTO, model prompt or search payload.
    """
    raw = json.loads(material_row['content_json'])
    rid = revision_id(raw)
    if not rid:
        return None, None
    row = conn.execute('SELECT * FROM document_revisions WHERE id=? AND material_id=?', (rid, material_row['id'])).fetchone()
    if not row or not raw.get('document_dir'):
        raise HTTPException(409, 'Saved document revision is unavailable')
    manifest = json.loads(row['manifest_json'])
    if manifest['source_sha256'] != raw['document']['source_sha256']:
        raise HTTPException(409, 'Saved document revision does not match the material')
    return manifest, Path(raw['document_dir'])


def staff_material(conn, mid, user):
    from .authoring import resolve_material
    live_actor(conn, user, staff=True)
    return resolve_material(conn, mid, user)[0]


def active_job(conn, mid):
    return conn.execute("SELECT * FROM document_jobs WHERE material_id=? AND status IN ('queued','running')", (mid,)).fetchone()


def latest_job(conn, mid):
    return public_job(conn.execute('SELECT * FROM document_jobs WHERE material_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (mid,)).fetchone())


def enqueue_job(conn, mid, user, request_id, expected_revision):
    """Requires BEGIN IMMEDIATE; original validation runs before accepting a job."""
    row = staff_material(conn, mid, user)
    payload_hash = fingerprint({'expected_revision': expected_revision, 'requester_id': user['id']})
    prior = conn.execute('SELECT * FROM document_jobs WHERE material_id=? AND request_id=?', (mid, request_id)).fetchone()
    if prior:
        if prior['payload_hash'] != payload_hash:
            raise HTTPException(409, 'Document request ID was reused with different content')
        return public_job(prior)
    raw = json.loads(row['content_json'])
    if revision_id(raw) != expected_revision:
        raise HTTPException(409, 'Document revision changed; reload before processing')
    if active_job(conn, mid):
        raise HTTPException(409, 'A document processing job is already active')
    path = Path(row['file_path']) if row['file_path'] else None
    if not path or path.suffix.lower().lstrip('.') not in FULL_FORMATS or raw.get('kind') == 'link':
        raise HTTPException(422, 'Full document processing requires an original supported document')
    try:
        source_sha256, page_count = source_identity(path)
    except BundleError as exc:
        raise HTTPException(422, str(exc)) from None
    if not revision_id(raw):
        raw.update(processing='full_document', status='processing', excerpt='', warning=None)
        conn.execute('UPDATE materials SET content_json=? WHERE id=?', (canonical(raw), mid))
    jid = new_id()
    conn.execute('''INSERT INTO document_jobs(id,material_id,request_id,payload_hash,requester_id,requester_role,token_hash,
        status,created_at,page_count,expected_revision,source_sha256,source_path_hash,material_hash)
        VALUES(?,?,?,?,?,?,?,'queued',?,?,?,?,?,?)''',
        (jid, mid, request_id, payload_hash, user['id'], user['role'], getattr(user, 'token_hash', None),
         now(), page_count, expected_revision, source_sha256, fingerprint(str(path)), fingerprint(raw)))
    return public_job(conn.execute('SELECT * FROM document_jobs WHERE id=?', (jid,)).fetchone())


def job_actor(job):
    return AuthenticatedUser({'id': job['requester_id'], 'role': job['requester_role']}, job['token_hash'])


def check_job_target(conn, job):
    row = staff_material(conn, job['material_id'], job_actor(job))
    raw = json.loads(row['content_json'])
    if (revision_id(raw) != job['expected_revision'] or fingerprint(raw) != job['material_hash']
            or fingerprint(row['file_path']) != job['source_path_hash']):
        raise BundleError('Material source or revision changed during processing')
    digest, count = source_identity(row['file_path'])
    if digest != job['source_sha256'] or count != job['page_count']:
        raise BundleError('Document source hash does not match the original')
    return row


def fail_job(conn, job, error):
    conn.execute("UPDATE document_jobs SET status='failed',finished_at=?,error=? WHERE id=? AND status IN ('queued','running')", (now(), error, job['id']))
    row = conn.execute('SELECT * FROM materials WHERE id=?', (job['material_id'],)).fetchone()
    if row:
        raw = json.loads(row['content_json'])
        if not revision_id(raw) and fingerprint(raw) == job['material_hash']:
            raw.update(status='error', warning=error)
            conn.execute('UPDATE materials SET content_json=? WHERE id=?', (canonical(raw), row['id']))


def info_for(manifest, rid, created_at):
    blocks = [b for p in manifest['pages'] for b in p['blocks']]
    uncertain = any(b['quality'] == 'needs_review' for b in blocks) or any(p['status'] in ('needs_review','failed') for p in manifest['pages'])
    eligible = [b for b in blocks if b['quality'] != 'excluded']
    quality = 'needs_review' if uncertain else 'approved' if eligible and all(b['quality'] == 'approved' for b in eligible) else 'extracted'
    return {'revision_id': rid, 'source_sha256': manifest['source_sha256'], 'page_count': manifest['page_count'],
            'block_count': len(blocks), 'quality': quality, 'review_count': sum('review' in b for b in blocks),
            'parser': manifest['parser'], 'created_at': created_at, 'warnings': manifest['warnings'],
            'source_format': manifest.get('source_format') or 'pdf', 'has_rendered_pdf': bool(manifest.get('preview_pdf'))}


def add_revision(conn, mid, manifest, actor_id, parse_id, *, parent=None, request_id=None, payload_hash=None):
    rid, stamp = new_id(), now()
    info = info_for(manifest, rid, stamp)
    conn.execute('''INSERT INTO document_revisions(id,material_id,source_sha256,created_at,created_by,parse_id,
        parent_revision,manifest_json,info_json,request_id,payload_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (rid, mid, manifest['source_sha256'], stamp, actor_id, parse_id, parent, canonical(manifest), canonical(info), request_id, payload_hash))
    return info


def install_document(conn, job, manifest, root):
    current = conn.execute('SELECT * FROM document_jobs WHERE id=?', (job['id'],)).fetchone()
    if not current or current['status'] != 'running':
        raise BundleError('Document job was interrupted or superseded')
    row = check_job_target(conn, job)
    info = add_revision(conn, row['id'], manifest, job['requester_id'], job['id'], parent=job['expected_revision'])
    raw = json.loads(row['content_json'])
    raw.update(document=info, document_dir=str(root), processing='full_document',
               status='needs_review' if info['quality'] == 'needs_review' else 'ready',
               excerpt='', warning='; '.join(info['warnings']) or None, extracted_at=info['created_at'])
    conn.execute('UPDATE materials SET content_json=? WHERE id=?', (canonical(raw), row['id']))
    conn.execute("UPDATE document_jobs SET status='completed',finished_at=?,page_count=?,processed_pages=?,revision_id=?,error=NULL WHERE id=?", (now(), info['page_count'], info['page_count'], info['revision_id'], job['id']))
    return info


def review_document(conn, mid, user, payload):
    row = staff_material(conn, mid, user)
    identity = fingerprint({'actor_id': user['id'], **payload})
    prior = conn.execute('SELECT * FROM document_revisions WHERE material_id=? AND request_id=?', (mid, payload['request_id'])).fetchone()
    if prior:
        if prior['payload_hash'] != identity:
            raise HTTPException(409, 'Source review request ID was reused with different content')
        return {'document': public_document(json.loads(prior['info_json']))}
    raw = json.loads(row['content_json'])
    if revision_id(raw) != payload['expected_revision'] or not revision_id(raw):
        raise HTTPException(409, 'Document revision changed; reload before reviewing')
    if active_job(conn, mid):
        raise HTTPException(409, 'Wait for the active document processing job before reviewing')
    manifest, _ = get_document_manifest(conn, row)
    blocks = {b['id']: b for p in manifest['pages'] for b in p['blocks']}
    changes = payload['changes']
    if len({c['block_id'] for c in changes}) != len(changes) or any(c['block_id'] not in blocks for c in changes):
        raise HTTPException(422, 'Review block IDs must be unique and belong to this document')
    stamp = now()
    for change in changes:
        block = blocks[change['block_id']]
        block.setdefault('raw_text', block['text'])
        if 'text' in change:
            block['text'] = change['text']
        block['quality'] = change['quality']
        block['review'] = {'by': user['id'], 'at': stamp, 'reason': change['reason']}
    for page in manifest['pages']:
        if page['status'] == 'needs_review' and page['blocks'] and all(b['quality'] != 'needs_review' for b in page['blocks']):
            page['status'] = 'text'
    manifest = validate_manifest(manifest, reviewed=True)
    old = conn.execute('SELECT parse_id FROM document_revisions WHERE id=?', (payload['expected_revision'],)).fetchone()
    info = add_revision(conn, mid, manifest, user['id'], old[0], parent=payload['expected_revision'],
                        request_id=payload['request_id'], payload_hash=identity)
    raw.update(document=info, status='needs_review' if info['quality'] == 'needs_review' else 'ready')
    conn.execute('UPDATE materials SET content_json=? WHERE id=?', (canonical(raw), mid))
    return {'document': public_document(info)}


def share_supplements(conn, mid, user, payload):
    """Explicit draft-only source-note visibility revision; publication is separate."""
    row=staff_material(conn,mid,user)
    identity=fingerprint({'operation':'supplement_sharing','actor_id':user['id'],**payload})
    prior=conn.execute('SELECT * FROM document_revisions WHERE material_id=? AND request_id=?',(mid,payload['request_id'])).fetchone()
    if prior:
        if prior['payload_hash']!=identity:raise HTTPException(409,'Document request ID was reused with different content')
        return {'document':public_document(json.loads(prior['info_json']))}
    raw=json.loads(row['content_json'])
    if revision_id(raw)!=payload['expected_revision']or not revision_id(raw):
        raise HTTPException(409,'Document revision changed; reload before sharing source notes')
    if active_job(conn,mid):raise HTTPException(409,'Wait for the active document processing job before changing source-note visibility')
    manifest,_=get_document_manifest(conn,row)
    if not manifest.get('supplements'):raise HTTPException(422,'This document has no indexed supplementary source text')
    stamp=now()
    for item in manifest['supplements']:
        item['visibility']='student'if payload['visible_to_students']else'teacher'
        item['sharing_review']={'by':user['id'],'at':stamp,'reason':payload['reason']}
    manifest=validate_manifest(manifest,reviewed=True)
    previous=conn.execute('SELECT parse_id FROM document_revisions WHERE id=?',(revision_id(raw),)).fetchone()
    info=add_revision(conn,mid,manifest,user['id'],previous['parse_id'],parent=revision_id(raw),request_id=payload['request_id'],payload_hash=identity)
    raw['document']=info
    conn.execute('UPDATE materials SET content_json=? WHERE id=?',(canonical(raw),mid))
    return {'document':public_document(info)}
