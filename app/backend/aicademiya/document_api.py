"""Frozen authenticated Stage12 DTO/API boundary (no model or search calls)."""
import copy
import json
import mimetypes
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import Field, field_validator

from .authoring import resolve_material
from .document_bundle import BundleError, MAX_PAGES, MAX_FULL_UPLOAD_BYTES, StrictModel, asset_file, registered_assets, rendered_pdf_file
from .document_storage import (enqueue_job, get_document_manifest, latest_job, public_document,
                               public_job, review_document, revision_id, staff_material, share_supplements)
from .materials import MAX_UPLOAD_BYTES
from .version_context import is_staff


class JobRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    expected_revision: str | None = Field(max_length=100)

    @field_validator('request_id')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Request ID must not be blank')
        return value


class Change(StrictModel):
    block_id: str = Field(min_length=1, max_length=100)
    text: str = Field(default=None, max_length=100_000)
    quality: Literal['approved','excluded']
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Reason must not be blank')
        return value


class ReviewRequest(JobRequest):
    expected_revision: str = Field(min_length=1, max_length=100)
    changes: list[Change] = Field(min_length=1, max_length=100)


class SupplementSharingRequest(JobRequest):
    expected_revision: str = Field(min_length=1,max_length=100)
    visible_to_students: bool
    reason: str = Field(min_length=1,max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank_reason(cls,value):
        if not value.strip():raise ValueError('Sharing reason must not be blank')
        return value


def checked_document(conn, mid, user, rid, version_id):
    row, detail = resolve_material(conn, mid, user, version_id)
    raw = json.loads(row['content_json'])
    if revision_id(raw) != rid:
        raise HTTPException(409, 'Document revision does not match the selected material edition')
    manifest, root = get_document_manifest(conn, row)
    if manifest is None:
        raise HTTPException(404, 'No complete document is available')
    return manifest, root, detail


def page_projection(mid, page, rid, vid):
    def asset_url(name):
        params = {'revision_id': rid}
        if vid:
            params['version_id'] = vid
        return f'/api/materials/{quote(mid, safe="")}/document/assets/{quote(name, safe="/")}?' + urlencode(params)
    result = copy.deepcopy(page)
    result['image_url'] = asset_url(result.pop('image'))
    for block in result['blocks']:
        block['assets'] = [asset_url(name) for name in block['assets']]
    return result


def register_document_routes(app, db, queue, current_user, teacher_user):
    @app.get('/api/document-processing')
    def capability(user=Depends(current_user)):
        return {'available': queue.available, 'formats': list(queue.formats), 'max_upload_bytes': MAX_FULL_UPLOAD_BYTES, 'max_pages': MAX_PAGES}

    @app.post('/api/materials/{material_id}/document/jobs')
    def enqueue(material_id: str, payload: JobRequest, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            material = staff_material(conn, material_id, user)
            # GET and exact POST recovery remain possible after configuration is
            # removed; only NEW processing requires an available worker.
            prior = conn.execute('SELECT 1 FROM document_jobs WHERE material_id=? AND request_id=?', (material_id, payload.request_id)).fetchone()
            if not prior and not queue.available:
                raise HTTPException(503, 'Complete document processing is not configured')
            if not prior and Path(material['file_path'] or '').suffix.lower().lstrip('.') not in queue.formats:
                raise HTTPException(415, 'This source format is not enabled for complete processing')
            result = enqueue_job(conn, material_id, user, payload.request_id, payload.expected_revision)
        queue.notify()
        return result

    # Literal route precedes the dynamic job-ID route: lost POST outcomes can
    # recover using ONLY the client request ID, without a blind repeated POST.
    @app.get('/api/materials/{material_id}/document/jobs/requests/{request_id}')
    def request_outcome(material_id: str, request_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            staff_material(conn, material_id, user)
            row = conn.execute('SELECT * FROM document_jobs WHERE material_id=? AND request_id=?', (material_id, request_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Document job request not found')
            return public_job(row)

    @app.get('/api/materials/{material_id}/document/jobs/{job_id}')
    def job_outcome(material_id: str, job_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            staff_material(conn, material_id, user)
            row = conn.execute('SELECT * FROM document_jobs WHERE id=? AND material_id=?', (job_id, material_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Document job not found')
            return public_job(row)

    @app.get('/api/materials/{material_id}/document')
    def document_info(material_id: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            row, detail = resolve_material(conn, material_id, user, version_id)
            raw = json.loads(row['content_json'])
            manifest, _ = get_document_manifest(conn, row)
            pages = [{'number': p['number'], 'printed_label': p['printed_label'], 'status': p['status'],
                      'block_count': len(p['blocks']), 'review_count': sum('review' in b for b in p['blocks'])}
                     for p in manifest['pages']] if manifest else []
            supplements=[{k:s[k]for k in ('id','kind','source_part','source_node','page_hint','visibility')}|
                         {'characters':len(s['text']),'preview':s['text'][:240]}for s in (manifest or{}).get('supplements')or[]
                         if is_staff(user)or s['visibility']=='student']
            result={'document': public_document(raw.get('document')), 'pages': pages,
                    'latest_job': latest_job(conn, material_id) if is_staff(user) and not detail.get('_version_id') else None}
            if manifest is not None and 'supplements'in manifest:result['supplements']=supplements
            return result

    @app.post('/api/materials/{material_id}/document/supplements/sharing')
    def share_source_notes(material_id: str,payload: SupplementSharingRequest,user=Depends(teacher_user)):
        with db.connect()as conn:
            conn.execute('BEGIN IMMEDIATE')
            return share_supplements(conn,material_id,user,payload.model_dump())

    @app.get('/api/materials/{material_id}/document/supplements/{supplement_id}/text')
    def source_note_text(material_id: str,supplement_id: str,revision_id: str=Query(...,min_length=1),
                         version_id: str|None=None,user=Depends(current_user)):
        with db.connect()as conn:
            conn.execute('BEGIN')
            manifest,_,_=checked_document(conn,material_id,user,revision_id,version_id)
            item=next((s for s in manifest.get('supplements')or[]if s['id']==supplement_id),None)
            if item is None or not(is_staff(user)or item['visibility']=='student'):
                raise HTTPException(404,'Supplementary source text is unavailable')
            text=item['text']
        return PlainTextResponse(text,headers={'Content-Disposition':'inline','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @app.get('/api/materials/{material_id}/document/pages/{page_number}')
    def document_page(material_id: str, page_number: int, revision_id: str = Query(..., min_length=1),
                      version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            manifest, _, detail = checked_document(conn, material_id, user, revision_id, version_id)
            if not 1 <= page_number <= manifest['page_count']:
                raise HTTPException(404, 'Document page not found')
            return page_projection(material_id, manifest['pages'][page_number - 1], revision_id, detail.get('_version_id'))

    @app.get('/api/materials/{material_id}/document/assets/{asset_path:path}')
    def document_asset(material_id: str, asset_path: str, revision_id: str = Query(..., min_length=1),
                       version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            manifest, root, _ = checked_document(conn, material_id, user, revision_id, version_id)
            if asset_path not in registered_assets(manifest):
                raise HTTPException(404, 'Document asset not found')
            try:
                path = asset_file(root, asset_path)
            except BundleError:
                raise HTTPException(404, 'Document asset is unavailable') from None
        return FileResponse(path, media_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',
                            headers={'Content-Disposition': 'inline', 'Cache-Control': 'private, no-store',
                                     'X-Content-Type-Options': 'nosniff'})

    @app.get('/api/materials/{material_id}/document/pdf')
    def rendered_document(material_id: str, revision_id: str = Query(..., min_length=1),
                          version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            manifest, root, _ = checked_document(conn, material_id, user, revision_id, version_id)
            try:
                path = rendered_pdf_file(root, manifest)
            except BundleError:
                raise HTTPException(404, 'Rendered source PDF is unavailable') from None
        return FileResponse(path, media_type='application/pdf',
                            headers={'Content-Disposition':'inline','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @app.post('/api/materials/{material_id}/document/reviews')
    def review(material_id: str, payload: ReviewRequest, user=Depends(teacher_user)):
        # Frozen codepoint/batch bounds apply before copying a full manifest;
        # the existing global ASGI JSON byte limit is preserved.
        value = payload.model_dump(exclude_unset=True)
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return review_document(conn, material_id, user, value)

    @app.get('/api/materials/{material_id}/document/reviews/{request_id}')
    def review_outcome(material_id: str, request_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            staff_material(conn, material_id, user)
            row = conn.execute('SELECT info_json FROM document_revisions WHERE material_id=? AND request_id=?', (material_id, request_id)).fetchone()
            if not row:
                raise HTTPException(404, 'Source review request not found')
            return {'document': public_document(json.loads(row[0]))}
