# EDUC7703 Sample App — Historical Integration Contract

> 初始样例契约。当前应用为AIcademiya Stage16 R4/API0.11/schema9；当前入口与模块契约索引见 `../docs/project-review-20261014/README.md`。本文保留初版字段、品牌、预算和权限模型供历史对照。

Date: 2026-10-03. This file is the shared contract for the first working sample. Read `../docs/requirements-review.md` §3 and §11, plus `../research/course-analysis/README.md`. Do not modify original course/research files.

## Scope and constraints

- Local-first working Web app; PVE deployment packaging follows. No actual PVE/server changes today.
- HARD deadline 2026-10-03 21:00 Asia/Shanghai (UTC+08). Stop feature work before 20:35; leave time to verify and checkpoint. Children finish bounded first passes much earlier, not wait for cutoff.
- Main + at most 3 children = at most 4 workstreams. Never edit another lane's files or shared Hermes/model environment.
- Main owns contract, integration, launchers, deployment, browser verification.
- Backend lane owns `backend/` only. Frontend lane owns `frontend/` only. Content lane owns `sample_data/` only. Ask parent via findings for contract changes; keep compatibility.
- Python 3.13, FastAPI, SQLite; project-local `app/.venv`. React + TypeScript + Vite frontend; use npm local. Parent installs Python common dependencies; frontend owns npm install.
- Bilingual English/Chinese interface switch. Teaching default English.
- Session 4 first: 22 question units incl image matching; Session 2: 9 core + choice of 5 Pong OR 5 Bray questions (14 active path, not 19 mandatory).
- Reference reveal default `after_attempt`: attempted at least once, student explicitly requests reveal; hints first. Teacher configurable.
- Save answers/revisions and conversations; explicit student submission and teacher confirmation; no formal automatic grade.
- AI modes `demo` and `openai`. Demo visibly labelled, deterministic learning-feedback preview, never misrepresented as LLM. Real OpenAI-compatible endpoint from settings/env; failures remain visible, never silently fallback to demo.
- Model not yet ready: another user session is setting up `qwen3.8-27B`; do not touch that service. Main researches Codex subscription proxy separately. No keys committed/logged/exposed in responses.
- Demo identities are synthetic, not real class records. Real login/registration can be implemented but browser QA uses explicit local demo buttons. Public deployment must disable demo authentication.

## App identity and ports

UI title `Akademiya`, with `EDUC7703` retained as the course code. Light refined editorial/academic design, warm neutral surfaces, deep teal primary accent, excellent readable type. No need to copy MagicSchool branding. Main workspace: course navigation, central dialogue, right task/answer pane. Teacher view genuinely editable, not decorative.

Backend: `http://127.0.0.1:18773`. Frontend dev: `http://127.0.0.1:18774` proxies `/api` to backend. Built frontend served by backend for one-command use. Credentials: cookie HttpOnly, same-origin Vite proxy. Dates ISO8601. IDs strings. JSON snake_case. All `/api` errors return `{detail: string}` with appropriate status.

## Core JSON types

Implemented addendum: see `AUTH_CHANGE.md` for teacher-provisioned student accounts, first-login password gate and change-password routes. `User` also returns `must_change_password: boolean`. Teacher `instructions` remain visible to teachers and internal model context only; student SessionDetail keeps the field as an empty string.

Web-search addendum: chat requests accept `web_search:boolean` (default false). False skips search planning/provider entirely; true requires a forced `web_search` tool call using public-only context. Both student and teacher preview composers expose this switch. Its value participates in request identity; changing it requires a new request_id, while omitted/false preserve old fingerprint semantics. `AiStatus.web_search` returns `{enabled:boolean,configured:boolean,provider:'tavily'}` without credentials. `Message.citations[]` may additionally include `url:string` and `kind:'web'`; all actual retrieved URLs are retained even if the model omits citations. UI labels them as retrieved sources, not all necessarily used claims. Existing course citations are unchanged. Search config `EDUC_WEB_SEARCH_ENABLED` + `TAVILY_API_KEY` controls server availability, not individual chat choices. No new search endpoint; see WEB_SEARCH.md.

```ts
type User = {id:string; name:string; email:string; role:'teacher'|'student'};
type AiStatus = {mode:'demo'|'openai'; configured:boolean; base_url:string; model:string; last_error?:string|null};
type Course = {id:string; code:string; title:string; description:string; student_count:number; join_code?:string};
type SessionSummary = {id:string; course_id:string; title:string; subtitle:string; number:number; status:'draft'|'published'; question_count:number; estimated_minutes:number; learning_objectives:string[]; student_status?:'not_started'|'in_progress'|'submitted'|'confirmed'|'needs_revision'};
type Group = {id:string; title:string; kind:'core'|'reading'; description?:string};
type Question = {id:string; group_id:string; ordinal:number; type:'open_response'|'reading_response'|'fill_in_blank'|'single_choice'|'image_matching'; prompt:string; options:string[]; answer_slots:number; images:{label:string;url:string;alt:string}[]; source_label:string; hint?:string};
type Material = {id:string; title:string; kind:string; visibility:'student'|'teacher'; source_label:string; status:'ready'|'processing'|'needs_review'|'error'; excerpt:string; download_url?:string|null; warning?:string|null};
type SessionDetail = SessionSummary & {instructions:string; reference_policy:'after_attempt'|'after_feedback'|'after_submit'; teaching_language:string; groups:Group[]; questions:Question[]; materials:Material[]};
type Attempt = {question_id:string; answer:string; revision_count:number; updated_at:string; reference_revealed:boolean; revisions?:{answer:string;created_at:string}[]};
type Message = {id:string; role:'user'|'assistant'; content:string; question_id:string|null; created_at:string; mode:'demo'|'openai'|'system'; intent?:'answer'|'ask'; citations?:{source_label:string;text?:string}[]};
type Submission = {status:'not_started'|'in_progress'|'submitted'|'confirmed'|'needs_revision'; submitted_at:string|null; reviewed_at:string|null; teacher_note:string};
type Progress = {answered:number; total:number; active_question_ids:string[]; current_question_id:string|null};
type Workspace = {session:SessionDetail; user:User; selected_reading:string|null; attempts:Record<string,Attempt>; messages:Message[]; progress:Progress; submission:Submission; ai:AiStatus};
type StudentRow = {user:User; answered:number; total:number; selected_reading:string|null; status:Submission['status']; last_active:string|null; submitted_at:string|null};
```

- Student payloads never contain teacher reference answers or teacher-only material excerpts. `Question.hint` is non-answer guidance, not required. References only through gated endpoint.
- Teacher detail includes `reference_answers: Record<question_id,string>` in addition to SessionDetail, enabling editable key.
- Questions/options remain English teaching content even when UI locale is zh. UI labels/messages are bilingual.
- All arrays below are direct arrays unless an object response is specified.

## HTTP API

### Session/auth

- `GET /api/health` -> `{status:'ok'}`
- `GET /api/bootstrap` -> `{app_name:string,demo_enabled:boolean,default_locale:'en',ai:AiStatus}` (no secret values)
- `POST /api/auth/demo` body `{role:'teacher'|'student',student_index?:1|2}` -> `{user:User}` + cookie; only when demo enabled. Teacher and two synthetic students.
- `POST /api/auth/login` body `{email,password}` -> `{user}` + cookie.
- `POST /api/auth/register` body `{name,email,password,join_code}` -> `{user}` + cookie, student only.
- `GET /api/auth/me` -> `{user}` or 401. `POST /api/auth/logout` -> `{ok:true}`.

### Course/session/workspace

- `GET /api/courses` -> Course[] scoped to user.
- `POST /api/courses` teacher body `{title,code,description}` -> Course.
- `POST /api/courses/join` student body `{join_code}` -> Course.
- `GET /api/courses/{course_id}/sessions` -> SessionSummary[]. Students published only.
- `POST /api/courses/{course_id}/sessions` teacher body `{title,subtitle?,number?,instructions?,learning_objectives?}` -> SessionDetail, initially draft.
- `GET /api/sessions/{session_id}` -> SessionDetail; teacher gets reference_answers too.
- `PATCH /api/sessions/{session_id}` teacher body partial `{title,subtitle,instructions,learning_objectives,reference_policy,teaching_language,status,questions,reference_answers}` -> SessionDetail. Question type exact fields above. Keep unknown metadata off student API.
- `GET /api/sessions/{session_id}/workspace` -> Workspace, students own; teacher own preview workspace distinct from actual students.
- `POST /api/sessions/{session_id}/reading` body `{group_id:'II-Pong'|'II-Bray'}` -> Workspace; stores choice and recalculates active question denominator. Preserve other branch records when switching, don't count them. Do not allow changes after confirmed unless reopened.
- `POST /api/sessions/{session_id}/answers/{question_id}` body `{answer:string}` -> Workspace; preserve revision history, reject whitespace-only. No LLM request.
- `POST /api/sessions/{session_id}/chat` body `{message:string,question_id:string|null,intent:'answer'|'ask',request_id?:string}` -> Workspace after saving user+assistant messages. Answer intent with active qid saves a revision; ask intent does not. Include current task/material context. UI displays thinking while awaiting. Basic non-streaming first, no pretend streaming.
- `POST /api/sessions/{session_id}/references/{question_id}` -> `{question_id,reference:string,source_label:string}` gated by policy and actual student's attempt. First default attempt prerequisite returns 409 if not met. Persist reveal marker.
- `POST /api/sessions/{session_id}/submit` body `{}` -> Workspace. Require all active question units nonempty; does NOT require correct answers, reveal, or optional quizzes. Missing reading choice = 409. Teacher can request revisions.
- `GET /api/sessions/{session_id}/export` -> own JSON downloadable conversation+answers; teacher preview own only.
- `GET /api/assets/{asset_path:path}` -> sample image bytes. Only known safe public diagram asset paths. Never serve arbitrary research folder.

### Teacher observation

- `GET /api/teacher/sessions/{session_id}/students` -> StudentRow[] (teacher owns course).
- `GET /api/teacher/sessions/{session_id}/students/{user_id}/workspace` -> Workspace (read only target), including teacher-only SessionDetail/reference_answers if useful.
- `POST /api/teacher/sessions/{session_id}/students/{user_id}/review` body `{status:'confirmed'|'needs_revision',note:string}` -> updated Workspace. Must be a submitted/confirmed/revision-target attempt, no confirmation of never-started work.
- `GET /api/teacher/sessions/{session_id}/students/{user_id}/export` -> JSON.
- `POST /api/sessions/{session_id}/materials` multipart `file`, `visibility=student|teacher`, `kind=reading|worksheet|answer_key|slides|reference` -> Material. Support txt/md/pdf/docx/pptx extraction, retain original privately. Scan detection -> needs_review, not success with empty text. UI can poll session after processing. First version parsing preview is enough; auto-turning arbitrary upload into final worksheet is NOT required.
- `DELETE /api/sessions/{session_id}/materials/{material_id}` OPTIONAL (archive record only, no permanent file deletion).
- `GET /api/materials/{material_id}/download` authenticated/role-checked binary.

### Model settings

- Server-only teaching-router addendum (2026-10-04): `EDUC_AI_PROVIDER=teaching-router` plus exact openai/base URL `http://127.0.0.1:18280/v1`/model `teaching-qwen27b` opts into 600s non-streaming completion and standard outbound `user` HMAC scope. Scope is derived from authenticated server user/role/activity plus phase and persisted installation secret, never client-supplied; no incoming API/UI schema change. Other providers/demo retain existing behaviour. Details and deployment boundaries: DEPLOYMENT.md.

- `GET /api/teacher/settings` -> `{ai:AiStatus,api_key_set:boolean}`. Nonteacher bootstrap only safe mode/model status (base_url may be omitted if necessary but use empty string).
- `PUT /api/teacher/settings` body `{mode,base_url,model,api_key?:string}` -> same response. Omitted key preserves; never echo key. Environment alternative `EDUC_AI_MODE`, `EDUC_AI_BASE_URL`, `EDUC_AI_MODEL`, `EDUC_AI_API_KEY`.
- `POST /api/teacher/settings/test` -> `{ok:boolean,message:string,model:string,mode:string}`. Real mode makes bounded actual request. Do not fabricate connectivity. Local services may need empty API key.

## Sample data contract (content lane -> backend lane)

`sample_data/catalog.json`:
```json
{"schema_version":1,"course":{"id":"educ7703","code":"EDUC7703","title":"Language Testing & Assessment","description":"..."},"sessions":[{"id":"session-4","course_id":"educ7703","number":4,"title":"What makes a good test?","subtitle":"Principles of language assessment","status":"published","estimated_minutes":40,"learning_objectives":["..."],"instructions":"...","reference_policy":"after_attempt","teaching_language":"en","groups":[{"id":"T1","title":"...","kind":"core"}],"questions":[{"id":"S4-T1-Q01","group_id":"T1","ordinal":1,"type":"fill_in_blank","prompt":"...","options":[],"answer_slots":1,"images":[],"source_label":"Session 4 worksheet · Task 1 Q1"}],"reference_answers":{"S4-T1-Q01":"practicality"},"materials":[{"id":"s4-slides","title":"Session 4 slides","kind":"slides","visibility":"student","source_label":"...","status":"ready","excerpt":"curated text for tutoring","file_path":"materials/s4-slides.pdf"}],"research_notes":["teacher-only provenance or issues"]}]}
```
- IDs exact from existing question-map; S2 group ids `I`, `II-Pong`, `II-Bray`, first core, other reading.
- M17 diagram files copied to sample_data/assets and Question.image URL `/api/assets/s4-graph-a.png`, etc. No answer revealed in student alt text (e.g. "Scatter plot A", not "positive correlation").
- Content lane may include reasonably sized original course copies under sample_data/materials, explicitly classify teacher/student. Avoid bundling all thousand-page guides by default. Include worksheet/answers, two slide sets, two selected-reading PDFs. Do not embed real student records.
- Source research findings don't automatically become official teacher corrections. For missing S2 Part I key, label instructor-review draft if you synthesize grounded teaching guidance. Material conflicts need teacher-visible notes, but do not lecture students with internal audit notes.
- Backend loads catalog on first run idempotently, database `app/data/educ7703.sqlite3`; uploads in app/data/uploads; NEVER overwrite edited course data at every restart. Support `EDUC_DATA_DIR` to select an isolated QA/deployment data directory. Provide `backend/requirements.txt` for installation.

## Main acceptance checks

Real browser teacher -> preview -> student (synthetic) -> answer/hint -> reference -> reload -> history -> submit -> teacher sees answers/revisions/chat -> confirms; second student cannot see first; S2 active count 14 after choosing one reading; 3 plots visible; real versus demo mode unambiguous. Need usable no-model mode while local model setup proceeds. Browser/mobile basic responsive check, no horizontal layout break. Avoid unrelated feature expansion.
