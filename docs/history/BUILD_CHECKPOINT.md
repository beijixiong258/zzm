# Akademiya · 历史样例checkpoint

> 当前入口：`../project-review-20261014/README.md`、`DEPLOYMENT_STAGE16_RESULT.md`。生产Stage16 R4/API0.11/schema9已核验。下文保存旧样例的形成记录、预算与当时状态。

## Historical delivery

Stage3 guided teaching is deployed; see STAGE3_CHECKPOINT.md and DEPLOYMENT_STAGE3_RESULT.md. All dated restrictions, unfinished tasks and older release paths below are historical.

## Historical next-stage development

User authorized AIcademiya stage2 on 2026-10-05 with no time limit and up to four agents. Current implementation/ownership/verified state is in **STAGE2_CHECKPOINT.md**, API/data contract in **STAGE2_CONTRACT.md**. The dated deadlines and pending tasks below are historical. No live deployment changes are authorized by this local development task.

## Current deployment — supersedes historical completion notes below

2026-10-04: Ubuntu LAN application and three-worker teaching-router are deployed and running. The earlier “not deployed / GPU paused / pending parent verification” passages below are archived development milestones, not current operation instructions. Read SERVER-LAN-DEPLOYMENT.md and TEACHING-ACCEPTANCE.md first. Production now has three explicitly authorized trial users (TESTTEACHER/TESTSTUDENT1/TESTSTUDENT2); LAN-only, demo/search disabled. New-password policy is8+ characters with a letter and a digit; backend170/frontend33 tests passed. Earlier users=0 statements are historical. Do not load the old8027 models alongside the teaching replicas. Current session deadline21:00 Asia/Shanghai; no unattended continuation after server shutdown.

## Historical final state

2026-10-04 shared-prefix follow-up: teaching-router only now uses one student-free static system + first-user server-generated dynamic envelope (attempt/intent; nested student answer untrusted). Cloud/demo unchanged. Added read-only `tools/warm_teaching_prefix.py`: default lists topic IDs, explicit session+question warms one topic, default v100 only, no private prompt output. Backend **150 passed** (8 new tests), bash syntax/py_compile passed; report `artifacts/teaching-router/shared-prefix-backend-tests.xml`. Commands and real API/router validation steps in DEPLOYMENT.md. No remote/model/warm calls, original/private data edits or Git operations. Actual tokenizer/template hits and GPU warm remain unverified; search/tool prefixes require separate verification. This supersedes the older attempt-in-system/shared warm advice below.

2026-10-04 router/Linux addendum: opt-in EDUC_AI_PROVIDER=teaching-router with exact http://127.0.0.1:18280/v1 / teaching-qwen27b adds server-derived anonymous standard user scope and 600s timeout; demo/cloud unchanged. Linux .env.example + tools/start-linux.sh added. Latest backend142/frontend33 tests and build passed; synthetic49 API +16 core browser +5 password checks passed, owned QA server stopped. Python3.12/Linux x86_64 binary dependency resolution and bash syntax passed, not a Linux deployment. No remote access, Git init/commit, real model/Tavily call, private local-settings/data or original material change. sample_data is now Git-ignored for separate private upload per current user instruction. See DEPLOYMENT.md Ubuntu section; actual router/KV hits/Linux/HTTPS remain unverified.

Current search behaviour: students and teacher previews have an explicit per-message switch, default off and remembered locally per account/session. Off bypasses query preparation/Tavily; on forces web_search with public-only context (private teacher context only in final tutoring). Model NO_SEARCH is no longer accepted. Every retrieved source has a directly clickable persisted link even when the model omits citations; empty results get a notice. Key/global availability stay in ignored local-settings.json; AI mode remains demo. Latest backend132/frontend33 tests and production build passed; original49 HTTP/21 browser checks plus8 live-Tavily switch/source checks passed. The latter used2 real searches and6 labelled model protocol requests, zero Qwen requests. See WEB_SEARCH.md. Model resource pause remains in force; actual forced-tool compatibility/quality awaits user confirmation. Owned QA services stopped; never restart another active app/model process merely to apply edits.

The sample is implemented and verified; all delegated branches have returned. There is no pending child to poll. Before the Tavily addition: backend105 tests, frontend24 tests/build,49 real API requests,16 core browser checks +5 first-password checks.13 screenshots,0 page errors. First-login password change, teacher private instructions and materials, failed-model idempotent retry, word bank and Markdown display are included. Use the follow-up paragraph above for current test counts.

Entry: start.cmd -> http://127.0.0.1:18773 after startup. README.md and VERIFICATION.md describe tested scope; DEPLOYMENT.md is preparation only. All owned QA services were stopped. The default app/data DB has not been filled with QA records. tools/verify_delivery.py performs the final file/link/guard check without inference.

local-settings.json pre-fills the user endpoint/model but remains mode=demo. Seven real-model turns completed before the resource pause; further inference is paused until the user confirms availability. Do not infer idle capacity from a healthy endpoint. No automatic background continuation is scheduled.

## Authorized target

2026-10-03 local sample build, hard stop 21:00 Asia/Shanghai. At most 4 concurrent workstreams including main. Feature freeze by 20:35 if still working; earlier working handoff is fine. No requirement to use the entire budget.

## Decisions

- App under `D:/HermesProjects/EDUC7703/app`; existing archives/research not moved.
- Product name Akademiya. EN/ZH UI, English learning conversation.
- FastAPI + SQLite + React/TypeScript/Vite. Source contract in CONTRACT.md.
- Local backend 18773, frontend dev 18774. At initial check both were free.
- ~40 students, 5–8 concurrent; external PVE access is eventual deployment target, not actual server change tonight.
- User endpoint: OpenAI-compatible `http://192.168.32.5:8027/v1`, exact model ID `qwen27b-q8`, arbitrary placeholder key permitted. Connectivity and seven short teaching probes completed; further inference is paused per user's resource coordination instruction. Do not restart/change the model service.
- Default reference policy: attempted once -> student may request sample; first offer hints.
- Teacher confirmation required, no formal auto grades.

## Scope for first pass

1. Self-contained backend auth, course/session data, workspace persistence, gated references, submission and teacher review, upload preview, model settings.
2. Real interactive frontend teacher/student workspaces, bilingual labels, task images, progress, history and settings.
3. Faithful Session 4 (22 units) + Session 2 (9 core + one of two 5-question readings) sample catalog and sources.
4. Parent integrates, exercises API/browser, adds local clickable launcher and PVE-ready instructions/container files. Do not claim PVE tested when only local verification is done.

## Evidence so far

- Course research: `../research/course-analysis/README.md`, question-map.json, original images and excerpts.
- Research validation: 41 candidate question stems match source DOCX, 14 scan pages OCR completed, original files unchanged.
- Runtime: Windows11, Node26.7.0, npm11.19.0, Python3.13.5, uv available, Docker not installed. No need to install Docker locally for this sample.
- Official Hermes subscription proxy docs currently list Nous/xAI adapters; Codex not verified. Do not invent compatibility.

## Initial setup history

Three initial children (`deleg_6956d391`) completed backend, frontend and sample data. Follow-up AI-context (`deleg_64c2799d`) and authentication (`deleg_394c7934`) branches also completed and were independently verified. Parent owns final integration. Python .venv and local npm dependencies are ready.

Model route check: `hermes proxy providers` on installed runtime lists only nous/xai; `codex-cli 0.147.0` is installed but `codex login status` says Not logged in. Do not copy Hermes OAuth credentials into Codex CLI or create an unofficial proxy. Wait for the local model endpoint or an explicitly configured legitimate provider. Core app work continues in visibly labelled demo mode.

Backend steered to support `EDUC_DATA_DIR` and provide `backend/requirements.txt`. Parent must use a separate QA data directory for acceptance; never clear the user's sample database to retry tests.

## Deferred user requirement (2026-10-03)

Implemented after the main flow, as confirmed by the user: teacher-issued temporary credentials MUST change password first; invite self-registration and synthetic demo accounts exempt. Backend gates protected business routes, clears the flag and revokes old sessions on change; frontend forces the setup screen. Real API + browser gate/layout/reload checks passed with runtime-only synthetic credentials, without typing real passwords into a browser.

## Historical integration snapshot 2026-10-03 17:18 (not current)

- Parent independently reran backend 33 tests, frontend 18 tests/build, sample_data original-document validation: passed.
- Parent `tools/run_integration.py`: real FastAPI+SQLite and built UI, 49 API requests and 14 browser checks passed. Screenshot evidence `artifacts/browser-integration/` (9 images); outputs `api-acceptance.json`, `integration-result.json`, `browser-result.json`. No mocked API. Explicit synthetic identities/answers; AI mode demo. Real Qwen not tested.
- Fixed frontend mismatch: submitted records now read-only like backend; teacher reopen allows edits. Added original word bank/group instructions. Fixed failed-model retry to reuse request ID and refresh server-saved work; actual unreachable-endpoint browser test passes without duplicate revisions/messages.
- Parent-owned QA service `proc_625a1d0b946a` remains on 18773 with QA data; MUST stop it before starting final local sample. Default app/data DB does not yet exist. All per-run ephemeral QA servers stop in runner finally.
- AI context fix child `deleg_64c2799d`/`sa-0-e8fc06de` has finished according to failed steer, result awaiting end-turn delivery. Do not poll artifacts. It was assigned server-only current-question reference context + tests; no HTTP schema changes.
- Additional discovered issue to fix once AI lane hands back: httpx trust_env=True on localhost can use Windows system proxy (test localhost:1 returned502/timeout; trust_env=False gave ConnectError). Isolated QA and launcher set child-only NO_PROXY. The model adapter itself still needs local endpoint proxy bypass validation.
- Wrote top-level start.cmd/setup.cmd, tools/launch.py, Dockerfile/compose.yaml/.dockerignore. Launcher check/smoke pending. Docker not installed; PVE/container build NOT verified.

## Historical integration snapshot 2026-10-03 17:50 (not current)

- AI reference-context child result received and independently verified: backend36 tests passed before parent's additions. Parent added local/private endpoint proxy bypass and source-ID citation recognition; dedicated AI/proxy/source tests20 passed. Do not change global proxy/OS settings.
- Live local model was supplied and probed BEFORE the subsequent resource-pause request: 7 serial real-model turns returned200, 6.62–11.05s (median8.32). Raw results/review in artifacts/live-model. No further inference is authorized until resource window confirmed. Correct diagram answer still elicited repetitive questioning: noted for later targeted prompt tuning, not hidden as all-quality-pass.
- Frontend24 tests + production build passed after adding safe Markdown rendering, forced-password view and teacher provision form. Changes are not fully auth-integrated until backend child returns.
- Auth backend child running: delegation `deleg_394c7934`, child `sa-0-d4d159b4`; only backend auth files. Parent owns frontend, ai.py plus local/source tests, tools, docs. Do not poll child artifacts.
- First-login frontend implements AUTH_CHANGE.md; tools/password_browser_check.mjs written, NOT yet exercised. Run `tools/run_integration.py --password` once child handed back.
- Parent-owned service proc_625a1d0b946a on18773 has been stopped. No default app/data DB yet. Launcher prerequisite check + fresh18775 smoke passed and port confirmed closed.
- Top-level README/DEPLOYMENT written with explicit Docker/PVE unverified boundary. start.cmd/setup.cmd exist. npm install must use --include=dev; scoped NODE_TLS_REJECT_UNAUTHORIZED=1 works (do not change shared environment).

## Model resource coordination — user instruction

The user is optimizing/benchmarking the same local model in another session. Before additional REAL model testing, establish an available resource window; endpoint health alone is NOT proof of idle resources. The previous seven-turn serial probe had already completed when the instruction arrived; its owned QA server stopped. Do not run new inference/load tests until availability is confirmed. Continue CPU-only/app demo/auth/browser work. Default user sample remains demo until deliberate switch.

## Resume rule

Read the final-state section, README, VERIFICATION and CONTRACT/AUTH_CHANGE. All branches are complete; do not replay old milestone TODOs. Check live time and current user instructions before further work, especially the model resource pause and original21:00 deadline. Remaining scope: arbitrary worksheet/new-group import, online OCR, unsent draft persistence/version snapshots, public PVE/HTTPS/restore verification and resource-approved model tuning/concurrency. Do not reset the user's database to refresh seeds.
