# Stage12 — complete PDF reading in a course

## Goal / authorization

User approved the proposed next step: solve known diagram failure modes, integrate complete document processing, then exercise one course from upload through teaching and clickable original-page citations. No time deadline (existing explicit boundary); monitor Codex and stop/checkpoint below1%. No paid/cloud OCR, no new models initially, no RAG/vector/Hindsight/voice expansion. Preserve originals, real accounts/courses/learning/config, immutable editions and private reference rules. Website English, reports Chinese. Work in isolated synthetic QA before retained-data deployment. Never rerun old cutovers. Protected AGENTS.md remains unchanged; its dated Stage2 scope does not supersede current explicit task.

Current source baseline: artifacts/stage12/baseline.json (514 files). Stage11 is live API0.9/schema8. This stage targets API0.10.0/schema9, additive storage, no automatic parsing/backfill of historical materials and no automatic course publication. Source originals stay read-only. Full-document path initially PDF (covers selected scanned chapter and317-page guide); existing Office/image/link/text preview behavior remains compatible and explicitly labelled preview, not claimed complete.

## Deployment/resource boundary

No existing model/router/process/unit/GPU/cache change while developing. Current Ubuntu now32GB RAM, NUMA0 memory only; obsolete NUMA1 binding MUST NOT be reused. Existing8027 and all three router workers remain untouched. Independent parser lane first validates CPU-only job execution, own temporary loopback18893, reasonable memory/threads, closes owned resources. Its result decides worker placement; do not declare GPU co-residency from idle/freeVRAM. Parent transport is an explicit trusted worker command (shell=False), initially exercised locally and with a bounded SSH job to the existing GPU server if viable; no new persistent public/network listener is necessary. Do not send classroom data to cloud OCR.

## Data model

- **Document revision**: immutable, exact-source-bound complete page/block representation. Distinct from course edition. Reprocess/correction creates a new revision; published editions retain old revision and old assets.
- **Processing job**: operational queue/run/outcome for one material/source and requester. Not teaching content or automatic publication. Parse success != quality approval.
- **Extraction quality**: `extracted` machine transcription, `needs_review` uncertain/reconstructed, `excluded` unsuitable; application may add `approved` only after explicit authorized source review. Never advertise extracted as certified zero-error.
- **Source review/correction**: explicit staff mutation with expected revision. Keep raw text, actor/time/reason and prior revision. Corrected draft does not rewrite old editions or student records.
- **Source citation**: exact material/revision/page/block and verbatim quote from evidence actually read for the current model request. Not a title-only guess or an invented URL. Private source citations cannot become student file access.

Parser bundle schema and worker CLI: STAGE12_DOCUMENT_BUNDLE.md. Validate exact page set, source SHA, unique block IDs, bounded manifest/rasters/assets, finite normalized boxes, safe relative filenames and no symlinks before installation. Do not expose raw filesystem paths/provider config. Retain raw parser output under owned uploads directory. Existing upload25MiB cap can remain for this PDF-first slice; do not silently widen global ASGI limits. Full processing cap1000PDFpages with explicit failure beyond limit, not partial success.

Use additive `document_jobs` and `document_revisions` tables (names frozen; columns implementation-owned). Keep immutable manifest JSON in revision rows (no absolute paths inside manifests). Each parse's assets reside in a new private directory below uploads/documents/; corrections reuse immutable raster/crop files, not hundreds of copied image sets. Material content_json receives safe `document` summary and private `document_dir` only on successful commit. Raw snapshots already preserve material JSON; verify publication/restore retain these bindings. Extend backup_data's exact current/snapshot path visitor for document_dir; preserve all files, including referenced old assets. No revision deletion or automatic document cleanup this stage.

## API frozen interface (all under existing auth)

Definitions:
`Job`: {id,material_id,status:queued|running|completed|failed,created_at,started_at:string|null,finished_at:string|null,page_count:number|null,processed_pages:number,error:string|null,revision_id:string|null}. Errors sanitized; no argv/paths/secrets. Do not claim per-page progress without actual worker observations.
`DocumentInfo`: {revision_id,source_sha256,page_count,block_count,quality:extracted|needs_review|approved,review_count,parser:{name,version,recipe},created_at,warnings:string[]}.
`PageSummary`: {number,printed_label:string|null,status:text|blank|needs_review|failed,block_count,review_count}.
`Block`: parser fields plus optional raw_text and review:{by:string,at:string,reason:string}; assets in HTTP response become authorized relative API URLs, never disk paths.
`Page`: parser Page fields with image_url:string replacing image; blocks include authorized asset URLs.

1. `GET /api/document-processing` current_user → {available:boolean,formats:["pdf"],max_upload_bytes:number,max_pages:number}. Pure capability, no model call or cross-user queue disclosure.
2. Existing POST `/api/sessions/{sid}/materials`: optional multipart `processing=preview|full_document`, defaultpreview for compatibility. UI selects full_document forPDF when available and labels nonfull behavior explicitly. Full upload saves original+material and enqueues atomically, returns existing Material DTO with statusprocessing and no fake excerpt; original retained on later failure. Unconfigured full request503, no silent fallback. Legacy formats/path unchanged.
3. `POST /api/materials/{mid}/document/jobs` teacher_user, body {request_id:string,expected_revision:string|null}. Current assigned staff only, current originalPDF only. Idempotent by material/request_id+same payload; conflicting reuse409. Duplicate active job409 or exact same job recovery. Recheck source+actor+current revision inside write lock at enqueue and commit; no concurrent stale completion over restore/review/new source. Job execution outside SQLite lock. Existing good document remains readable if retry fails. Returns Job.
4. `GET /api/materials/{mid}/document/jobs/{jid}` teacher_user → exact Job outcome; authorize current course assignment before revealing. `GET /api/materials/{mid}/document/jobs/requests/{request_id}` → exact Job by scoped request ID, registered before dynamic job route: this recovers a lost POST response when server job ID is unknown. GET-only recovery after uncertain write. Current worker owns child process lifecycle; startup marks formerlyrunning interrupted/failed, retains queued jobs. No blind endless retry.
5. `GET /api/materials/{mid}/document?version_id=...` current_user → {document:DocumentInfo|null,latest_job:Job|null,pages:PageSummary[]}. Same current/published/history/material-visibility authorization as resolve_material. latest_job only for staff draft; not frozen into curriculum or leaked to students. No content available returnsnull, not fabricated pages.
6. `GET /api/materials/{mid}/document/pages/{page}?revision_id=...&version_id=...` → Page. revision_id required and must match authorized current/snapshot material revision, otherwise409. Include all blocks with truthful quality for source review; model selection excludes unverified reconstruction. No anonymous/cross-course/draft/teacher-only bypass.
7. `GET /api/materials/{mid}/document/assets/{asset_path:path}?revision_id=...&version_id=...` → exact validated registered raster/crop in authorized manifest. Only safe existing bundle assets, inline image + private/no-cache/nosniff. No arbitrary raw/manifest/config/download traversal.
8. `POST /api/materials/{mid}/document/reviews` teacher_user body {request_id,expected_revision,changes:[{block_id,text?:string,quality:approved|excluded,reason:string}]}. Atomic bounded batch (1..100blocks), text at most100,000Unicodecodepoints, reason1..2,000codepoints and nonblank after trimming; preserve raw text. Idempotent exact receipt recovery via `GET /api/materials/{mid}/document/reviews/{request_id}` → {document:DocumentInfo};409stale/conflicting reuse. Produce new immutable revision and independent GET readback before UI clears edits. Do not allow review during active parse commit without explicit conflict.

Material DTO gains optional `document:DocumentInfo|null`; public_material whitelist prevents document_dir leak. Processing job details come from document GET, not continuously mutating curriculum JSON. Existing reprocess-preview endpoint must explicitly409 when full document exists rather than silently leaving stale full revision next to changed preview. Publication refuses an attached processing/failed full-document material with no valid revision; no unrelated library-file publication block. Correction/job completion invalidates saved teacher-preview revision through actual document identity, not job progress.

## Reader and citation integration (parent-owned)

Load document manifest only from already-authorized selected material rows, including selected course edition. Exclude answer_key and privateworksheet bodies as before; optionalquiz/reading use public only. Exclude needs_review/excluded blocks from authoritative model evidence; provide visible notice when a requested region is withheld, not a fabricated answer. Directory/heading + bounded page/block reads cover entire stored document, not first4k/50k. Use current learner request and question; allow explicit page selection and whole-document text search. No other-course filenames or private source content in web-search planner.

Add a bounded read-planning step for full-document materials using the configured model and genuine scoped index; exact reads selected by the plan, no unbounded agent loop. Preserve existing pathways when no full document exists. Reading context and user-specific selection belongs in dynamic envelope, not the stable system cache prefix. Keep bounded total request and per-read limits; source-review UI distinguishes current planned/static evidence from complete corpus. Validate final citation quote against the exact supplied block/revision, then create server URLs. Preserve raw transcripts and add citation metadata; no reconstruction of messages. False citation is visible failure, not auto-invented corrected quote.

## UI scope (parent-owned)

Use existing MaterialManager/Materials/TutorMessage. Add full-PDF status/progress/retry, original-versus-page/block viewer, quality warnings, bounded explicit correction/review action, and clickable page citations. Keep file queue/accepted-upload recovery, dirty guards, mobile fit and English copy. Do not make a separate website or demand human review of every page. Show known uncertain regions without claiming automatic recognition of every possible error. Students cannot see private material or teacher review controls. Published/history sources remain bound to their edition/revision.

## Acceptance

- Actual scanned chapter upload (fresh parse, not only imported static fixture) → completed exact10spreads → source review/correction if needed → explicit publication → genuine local teaching questions about late pages/tables → exact quoted source links.
-317page coverage and latepage269/317 access, known diagram quality boundary retained. Full raw/crops retained. Do not answer workbook exercises during extraction.
- Synthetictwo courses/two staff/student and publishedold/new editions: scope/visibility/revocation/trash/history/privacy. Anonymous401; no cross-course references; private answer keys not sent to read/search planner.
- Reprocess/review races, unknown acknowledgements GET recovery, restart, stale revision handling, originalhash mismatch; real binary+JSON backup/restore into NEW directory with old source paths unavailable.
- Existing backend/frontend/package and course/teacher-preview/feedback/security regressions. No exclusion to conceal errors. Test exact Linux runtime and resource noninterference before any release cutover.

## Ownership

Parser child: NEW tools/document_stage12/parser_worker.py, parser_probe.py, parser_helpers.py plus own focused tests and artifacts/stage12/parser; own server stage12-parser directory. No backend/frontend/service edits.
Backend storage child: backend/aicademiya/document_*.py; db.py/main.py/services.py/versions.py/teacher_preview.py; authoring.py only existingreprocess guard; tools/backup_data.py; NEW backend/tests/test_stage12_document_*.py. No modelreader/guided/evidence/frontend/deployment edits. It supplies get_document_manifest(conn, material_row) or equivalent documented helper for parent. Parent will edit authoring.selected_tutor_materials only after handoff (no concurrent shared-file edit).
Parent: contract/DTO/frontend/modelreader/guided integration, worker transport, app integration tests, packaging and deployment. Shared-file ownership transfers only with explicit handoff.
