# AIcademiya_V2 private Linux runtime

This guide covers **fresh installation and data-preserving upgrades**, not proof
that a deployment occurred. CT255 at `192.168.32.55:18773` is the configured
example. For an existing CT255 site, follow the upgrade sections and preserve
its accounts, learning records, installation secret and private configuration.
Fresh account/data bootstrap applies only to an empty installation; it is not
an instruction to copy retired CT254 data or reset an existing CT255 database.
Nothing here automatically operates PVE/SSH or changes the GPU/router services.

## Multimodal source teaching (Stage15, API0.10.0 / schema9)

The application keeps native text, machine-extracted Markdown/tables and original
page/region images as distinct source representations. Images requested by the
read planner enter actual multimodal model messages; storing a picture or showing
it in the UI is not model delivery. Original-image citations link the authorized
source page without inventing a literal quotation. Retrieval descriptions are not
verbatim source text. Image reads retain course/revision/edition/private/exclusion
boundaries; uncertain text extraction alone does not make source pixels disappear.

Where an explicitly provenanced full-page Markdown view overlaps native blocks,
default reading chooses a stable primary view. Approved original text retains
precedence; every original block remains available for explicit block reads.
Text cursors bind the selected sequence and policy, while image traversal stays
independent. UI counts distinguish supplied selected-view characters from retained
alternative blocks and their review/exclusion status. These are reading counts,
not unique source-character or semantic-accuracy scores.

The optional Stage15 page worker runs after CPU native preparation under the same
exclusive T10-B lease. Its root-owned SHA-pinned `AICADEMIYA_DOCUMENT_VISION_PROFILE`
and `AICADEMIYA_DOCUMENT_VISION_PROFILE_SHA256` select fixed model/projector/argv;
no upload chooses a command or model path. A private8192-token parser instance
produces page Markdown/regions; this does not reduce the64K teaching replicas.
Each selected page uses real multimodal input counting, up to4096output tokens,
no text KV reuse and no model retry. Prepared PNG input is bounded to4MiB/page.
All original blocks, source identity and source pixels survive append. Optional
page-transcription failures remain explicit with source representation retained;
job cancellation, deadlines and resource failures abort rather than masquerading
as successful inference. The final worker receipt distinguishes fresh completed
transcription from representation-only completion. A configured1000-page limit
is an admission bound, not a guarantee of recognition within the job deadline.

Teaching image requests require an explicitly projected healthy teaching worker;
images never fall back to a text-only worker or a text-only token estimate. The
current transport admits at most2PNG/JPEG/WebP images,4MiB total original image
bytes and60kUTF-8 text bytes. It checks full input+output against the actual worker
context and bypasses text snapshot restore/save. Other compatible free workers
can serve unrelated text while the vision GPU is busy. When no vision teaching
worker is available (including an exclusive document lease), the image request
returns a visible retryable503 instead of dropping its images.

## Complete materials (Stage14, API0.10.0 / schema9)

Full-document processing is a separate, explicitly configured path for PDF, PPTX,
DOCX, DOC, TXT, MD, PNG/APNG, JPG/JPEG and WebP. Enable the tested suffixes with
`AICADEMIYA_DOCUMENT_FORMATS`; the legacy default remains PDF until configured.
Complete uploads are bounded to64MiB/1000source pages or image frames; every image
frame, including APNG poster/default, is decoded under a16million-pixel limit.
The preview-only route keeps its25MiB limit. Without a worker, the UI says preview-only; an explicit full request fails
503 rather than pretending a short excerpt is complete. Existing materials are not
automatically reprocessed or republished during migration.

Schema9 adds document_jobs and immutable document_revisions, retaining the previous
25 application tables. The original PDF, all represented pages, source blocks,
rasters/crops and raw evidence are retained. Course publication pins the document
revision; source review creates a new draft revision, never rewrites published
student history. All page/image access follows current course, staff/enrollment,
visibility, trash and historical-edition rules. Global Admin is not a course-content
bypass. Answer-key/private worksheet bodies remain excluded from tutor aggregation.

Processing is a durable serial job, not a long upload HTTP request. The app remains
one-worker. Queued jobs survive restart; interrupted running jobs fail visibly and
require explicit retry. The UI exposes real state, not a guessed percentage. CPU
scanned-book processing can take many minutes. A failed retry retains any earlier
good document. If the exact previous attempt fully parsed and transferred its bundle
but the SSH process failed during shutdown, an explicit new retry can recover the
validated same-source output: source/page/assets/revision/actor checks still apply,
the failed attempt remains failed, and raw/recovery.json records reuse without a
model rerun. Partial or mismatched output is not promoted.

`extracted` means machine transcription, not human certification. `needs_review`
and `excluded` regions do not become authoritative tutor evidence. Assigned staff
may explicitly correct/approve/exclude individual blocks with a reason; raw text and
the old revision remain. `review_count` counts blocks carrying review audit, not
remaining errors. The reader shows the original next to text, source coordinates,
safe table markup, and crops/captions. Saving review is not publication.

The guided tutor and legacy chat support both targeted lookup and server-owned
sequential block/character cursors bound to account/course edition/source revision.
Accepted turns advance once; rejected responses and retries do not consume another
chunk. Read counters describe supplied eligible text; unresolved/excluded regions
remain explicit, not a claim of complete source recognition or model comprehension.
The generation schema requires explicit selector fields; quoted final-page lookups
must not silently restart a completed sequential cursor. This is not a claim that an entire book
fits into every prompt. No vector store or new search provider is required. Selected
reads are dynamic context; filesystem paths and private worker configuration never
enter the model. Source quotations must match the exact supplied revision/block
before the server creates authenticated original-page links. In an explicitly
Markdown-formatted HTML table cell, supported `<br>` tags may be matched as display
whitespace within that same cell. Such citations retain their unchanged quote plus
`quote_basis` and exact raw-source `quote_char_start`/`quote_char_end`; source markup
is not rewritten. Case, numbers, punctuation, other markup and cell boundaries
remain literal. Unavailable evidence,
invalid read plans/quotes and provider failures remain visible, never a demo fallback.

Supported Office notes, comments, foot/endnotes, headers/footers, diagram and alt
text retain native part/node locators, rather than guessed PDF pages. Supplementary
text stays out of student AI reads until explicit draft sharing and publication;
historical editions retain their own visibility. Original Office downloads still
contain embedded notes: this is an AI/source-note projection policy, not file redaction.

### Optional worker configuration

Set AICADEMIYA_DOCUMENT_WORKER_COMMAND to a trusted JSON string array; the app uses
shell=False and appends --input and --output. AICADEMIYA_DOCUMENT_WORKER_TIMEOUT is
seconds (default3600). No credentials belong in frontend settings or the release.
The worker must create a fresh output directory and the schema1 manifest defined
in STAGE12_DOCUMENT_BUNDLE.md. Do not configure an untested command as "available".

The supplied document_ssh_bridge.py can send one bounded source over existing SSH.
The remote document_worker_service.py performs native/Office preparation on CPU
before requesting GPU capacity. Native-only TXT/MD does not load a model or lease
a GPU. Visual processing requires an explicitly configured CUDA VLM and the fixed
exclusive lease; there is no co-resident teaching/document or CPU-model fallback.
Native/layout and independent RapidOCR verification remain CPU. A serial lock,
resource reserve and owned-process cleanup apply; it opens no persistent
public listener. Heartbeats cancel owned work on client disconnect. Use a dedicated
unprivileged worker identity, root-owned runtime/code/models, pinned host key and
forced-command-only SSH key for production. The historical install_worker_linux.py
sets up the baseline only; it does not establish the newer lease protocol. Use the
verified immutable worker release and matching forced-key binding. Test actual SSH
transfer/cancellation and the deployed user before enabling the app command.

Production worker jobs must NOT use the development Codex-quota guard. Runtime paths
can be set by AICADEMIYA_DOCUMENT_BASE, AICADEMIYA_DOCUMENT_RUNTIME and
AICADEMIYA_DOCUMENT_HOME. Keep runtime/models separate from received course files.
For CUDA, keep the verified offline CUDA runtime/libraries. The forced SSH command
fixes AICADEMIYA_DOCUMENT_GPU_UUID and AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET;
AICADEMIYA_DOCUMENT_CUDA_RUNTIME and AICADEMIYA_DOCUMENT_CUDA_LIBS can override
the root-owned defaults. Put the relocated runtime bin first in LD_LIBRARY_PATH,
and reject ldd references back into an operator home. The resource owner drains and
stops only the designated T10-B teaching service, then waits for actual GPU allocation
release before issuing a capability. V100/T10-A continue teaching. The parser closes
its owned processes before release; the scheduler restores the independent teaching
service only after the card is clear. Memory guards remain additional checks, not a
replacement for exclusive ownership. Client disconnect/timeout and lease expiry
must be tested through the installed identity. Never reactivate an old unleased
document command merely by removing a migration gate.

Bind existing independent OCR weights explicitly with AICADEMIYA_RAPIDOCR_MODELS;
missing dependencies remain a verification blocker, never an implicit download or
accuracy claim. Literal agreement preserves case, punctuation, digits and word
boundaries, with actual nontruncated generation metadata. It does not certify table
relationships or diagram edges. A configured model name is not proof of healthy replicas;
check the actual route and a real completion, retaining degraded-worker findings.

## Global accounts and assigned course staff (stage11, API0.9.0 / schema8)

The browser title is now AIcademiya on Login/global pages and AIcademiya · <actual
course code> on selected/course-scoped pages. It is no longer fixed to EDUC7703.
Course descriptions retain authored linebreaks/blanklines and use available banner
width; the edit dialog is responsive. Live course summaries show Sessions, Admins,
Teachers and Students, with singular labels at1. Staff counts use explicit active
course assignments/current global role; student counts use active Student enrollments,
not a whole-platform total or frozen published metadata.

Settings → Global User Accounts is administrator-only: all-role search/filter/pages,
create with a role, reviewed CSV/XLSX role import, role changes and reversible global
disable/restore. New accounts require a temporary password and first-login change.
Global CSV/XLSX uploads are both2MiB/max1000rows with actual ZIP expansion checks;
role may be supplied per row or selected as a default (Student). Existing same-role
accounts are skipped without name/password/status changes; role mismatch blocks
commit and requires a separate explicit role change. Staging stores hashes only;
committed rows/results support exact recovery/idempotency for24hours.

Settings → Course Students for Teachers lists ONLY their assigned courses. Assigned
staff can create/enroll existing Students with no password reset, import reviewed
student rosters, and remove/restore only the current course enrollment. Existing
course-removal30-day retention remains; it does not disable the global account or
remove other-course memberships. Registration toggle remains in admin Settings.

Global account roles are separate from course access. Administrators use Course
staff assignments within Global User Accounts to choose any course's LIGHT metadata,
then explicitly add/remove Admins/Teachers or Make primary manager. They do not gain
all teaching content automatically. Multiple assigned staff share course management;
teacher private previews remain keyed by each teacher. Teachers can view colleagues
but cannot grant global roles or staff assignments. Student controls remain restricted.

Migration adds course_staff and account_imports and a one-time backfill marker only;
all original23 table schemas/named rows remain. Backfill assigns existing owners;
new course/seed/local management claims establish membership. Restart does not restore
revoked assignments. The original owner_id remains the primary-manager pointer, and
primary transfer is explicit; removing/disabling a primary or leaving a course with
no active staff is refused, including trash. Global role/status writes serialize and
recheck live actor/target; self-demotion/disable and last-admin loss are blocked.
Staff→Student requires explicit assignment removal and prior primary transfer.
Role changes revoke target sessions, not passwords, learning, avatars or feedback;
Student→staff never silently converts old enrollments into teaching access. Former
staff draft learning is retained but not exposed through Student history.

Global disabling uses the existing archived_at with no NEW automatic purge deadline;
previous legacy student deadlines remain on no-op writes and clear only by explicit
restore. Account imports are create/skip only and do not bulk-promote old accounts.
If a former staff account is later subject to a legacy Student purge, durable
teaching/primary/trash references retain its disabled identity instead of deleting
history or breaking foreign keys. Expired owned import receipts are removed before
eligible account cleanup; unexpired receipts protect the identity until expiry.
After migration do not roll back solely by switching code symlinks: restore a matching
pre-upgrade data/config/code set, retaining historical material paths. All older
owner-only wording below describes earlier stages and is superseded by explicit
assigned-staff authorization in this release. No public ingress or model-service
change is included in this upgrade.

## Public-test security preparation (stage 10, API 0.8.0 / schema 7)

Settings → User Management → New student registration controls self-service signup.
Default preserves the existing OPEN policy and still requires a valid course invite.
Closing is enforced in the registration transaction; it does not log out existing
accounts or stop authorized teachers from provisioning students. Save is followed
by independent readback. The setting lives in the existing settings table and is
included in backup/restore. No user or learning rows are reset.

Question figures now require sign-in and an authorized owned/enrolled course and
edition. Saved historical references remain available under existing history rules;
unpublished drafts, another owner's course, trash and forced-password gates are
not bypassed. API responses, including private figures, use private/no-store except
successful revisioned avatars (private/no-cache). Previously downloaded figures
cannot be revoked retroactively.

The one-worker app uses bounded transient authentication/invitation limits. Login:
30/IP/minute and10/account/5minutes; registration30/IP/5minutes; password change
30/IP/5minutes plus10/account/5minutes; join20/account/5minutes.429 includes Retry-After.
Changing untrusted forwarded headers does not change identities. Restart resets
these windows; multiworker deployment requires coordinated throttling first.
Auth bodies are16KiB, otherJSON4MiB, multipart27MiB before parsing, with existing
per-file limits retained. Office and roster archives verify actual bounded deflate
output before Office readers; link fetch requests identity encoding and refuses
unexpected compression; image pixel bounds precede decoding.

Host/Origin, browser Fetch Metadata/Referer, nosniff, framing and cache protections
are enabled. CSP frame-ancestors is an anti-framing policy, not a complete XSS
sandbox. Native PDF previews and explicitly sandboxed HTML exports retain their
own policies. Existing scrypt/password/session compatibility is preserved.

**Private HTTP is NOT the public deployment configuration.** Before exposing a
public test, configure the actual HTTPS domain and certificate, HTTP→HTTPS redirect,
AICADEMIYA_COOKIE_SECURE=true and exact AICADEMIYA_ALLOWED_ORIGINS=https://that-host.
AICADEMIYA_ALLOWED_HOSTS may list exact additional hostnames; no wildcards. Set
AICADEMIYA_FORWARDED_ALLOW_IPS only to the actual reverse proxy source address;
that proxy must replace forwarded headers and preserve Host. Never trust '*'.
Restrict direct18773 network access to the proxy/maintenance sources; do not expose
PVE/SSH/18280/model services. A proxy in another CT needs a reachable PRIVATE bind,
not blindly127.0.0.1. Limit connections and upload sizes at ingress, enforce request
body/header timeouts, and retain sufficiently long inference-response timeouts
(the model's600s timeout is not an upload timeout). Application bounds do not
replace Internet DoS protection. Enable HSTS on the verified TLS ingress, not on
the private HTTP endpoint. No DNS/NAT/firewall/public-proxy change is implied here.

## Account avatar, feedback and brand arrangement (stage 9, API 0.8.0 / schema 7)

Settings → Account supports own static PNG/JPEG/WebP upload, replacement and removal.
A local centered preview is not saved until explicit Save avatar. The server enforces
5 MiB /16 million pixels, applies EXIF orientation, crops and re-encodes256×256 PNG
without metadata. Only normalized BLOB is retained in account_avatars, not the raw
photo or external URL. Current signed-in users may view profile images; anonymous,
archived-target and old revision reads are denied. Initials remain the fallback.

Settings → Feedback is available to all roles. Users submit text and view only their
own history/replies; admins additionally use Administrator inbox to reply and mark
New/Reviewed. Reviewed does not assert a fix. No SMTP/email, attachments, telemetry,
learning transcript capture or AI summarization is configured. Draft/retry state is
account-scoped in the browser; authoritative feedback and replies persist in SQLite.
Admin saves compare a revision and all UI writes require independent readback.

Migration adds account_avatars and feedback only; old21applicationtables/rows remain.
Backups include avatar bytes and feedback automatically, with no new file bindings.
Global account purge cascades avatar removal and sets feedback author to null while
retaining authored text; course-only learning purge does not remove either feature.
Keep matching pre-upgrade code/data/config for rollback. No existing avatar or feedback
is invented/backfilled during upgrade.

The sidebar uses the existing V4 green panel horizontally (mark left, wordmark/tagline
right). All eight logo assets are unchanged. The user-selected light-background green-line palette is now the normal Login
with working sign-in and registration. The sidebar stays dark green. Do not pass
previewAppearance into the production Login: explicit preview props intentionally
disable authentication controls and remain only for offline visual comparisons.

## Course lifecycle and branding upgrade (stage 8, API 0.7.0 / schema 6)

Course owners now use Course actions → Edit course / Move to trash. Editing only
changes draft code/title/description; it preserves ID, invitation, ownership and
published snapshots. Publish explicitly when student-facing metadata should change.

Course Home → Trash lists only the owner's removed courses, even if there are no
active courses left. Restore course removes the operational marker and reuses the
same course, invitation, sessions, material links, published editions and saved work.
It does not force sessions open or unarchive separately archived accounts/members.
There is no permanent-delete operation or timed course-trash purge in this release.

The additive course_trash table has course_id, trashed_at and trashed_by only. Old
course/table rows are not rewritten or automatically moved. Schema becomes6. Normal
lists hide trash; invitation signup/join and current/historical content endpoints
are closed while trashed. Pending guided/legacy feedback blocks moving that course
with409; it is not interrupted. Unrelated courses remain accessible.

While trashed, normal retention does not destroy its archived enrollment work or
student identities still referenced by that course. Existing independent archive
deadlines are retained, not renewed: their normal policy resumes after restoration.
Previously downloaded/cached data cannot be revoked by this operational state.
Backups include the marker table automatically; restore only into a new isolated root.

The generic sign-in card contains the complete V4 logo/AIcademiya/tagline (the
original green panel was superseded by the selected light palette in Stage9), with no course-specific EDUC7703 labels, redundant public header or anonymous
model badge. The signed-in sidebar retains model status and a complete panel brand.
Only non-book logo outlines were modestly strengthened; original V4 inputs and book
geometry remain unchanged. Brand links still honor unsaved-navigation protection.

## Clarity / Settings upgrade (stage 7, API 0.6.0 / schema 5)

This release keeps the existing storage schema and account/course/learning rows.
Global Settings contains Account plus admin-only AI Model, Web Search and User
Management. Course membership and publication remain course-scoped. The brand
link returns to Course Home and navigation warns before discarding unsaved edits.

The normal product has no feedback/demo mode selector or demo sign-in UI. A
normal application (`AICADEMIYA_DEMO_ENABLED=false`) cannot execute simulated
feedback even if a legacy saved/environment ai_mode is demo. Unconfigured or
unavailable services fail visibly; deterministic adapters remain only for
explicit isolated developer QA. `start.cmd` no longer opts into QA demo mode.
No old message modes or records are rewritten by this change. Older releases do not honor the new saved search overrides; rollback must use the verified matching code/data/config pair, not assume an unchanged schema makes settings semantics interchangeable.

Admins can save Tavily settings at Settings → Web Search. The server stores
`web_search_enabled` and `web_search_api_key` in the existing SQLite settings
table. Saved values override `AICADEMIYA_WEB_SEARCH_ENABLED` / `TAVILY_API_KEY`;
absent overrides inherit the existing environment. Blank key input keeps the
current key. Explicit clear writes an empty override so an environment key does
not silently return. These values are private and included in data backups;
GET responses reveal only key presence/source, never key values or fingerprints.
The learner's per-message search switch still defaults off.

Active AI Model shows the configured model and the result of the last explicit
connection check, not a continuously polled online status. Settings → AI Model
and Web Search tests use saved values; opening/saving the form does not probe.
Model checks make one small completion, search checks one bounded public query.
Check state/timestamp persists and invalidates when effective configuration
changes. Missing configuration is not a green connection status. Model settings
and Tavily settings remain admin-authorized server-side.

Restore rehearsal must explicitly disable saved search overrides as well as
environment settings, and blank saved model URL/model/key in the restored copy.
Setting mode=demo with demo auth disabled is no longer a simulation switch; the
safe restored copy is openai/unconfigured and search disabled. Never run probes
from a production-data clone that retains the same installation scope secret.

## Teacher-workbench upgrade (stage 6, API 0.5.0 / schema 5)

The teacher workbench combines saved-draft test chat, source review and explicit instruction-file import. Opening the pane does not call a model. Start/Resume is explicit; unsaved edits are not silently used. Saved content changes make an existing managed test stale until Reset my preview. Reset clears only that owner's unversioned test and refuses pending inference; it does not clear students, other sessions, historical editions or course content.

A new additive teacher_previews table records generation/revision bindings. No original row is rewritten at upgrade. Managed guided calls need preview_id; synchronous full-preview reading/answer/reference/submit actions carry the same ID as a query parameter. Stale or missing IDs fail visibly. The old non-guided chat endpoint remains unavailable for managed tests. Keep the current ID/revision through reserve and commit.

Source review uses actual evidence selection/ranking/truncation without a model call. It shows selected snippets and capacities separately; it is not a complete live request containing learner history/search. Instruction files are temporarily extracted privately and reviewed/edited before Apply to an unsaved draft; saving and publishing remain separate. Process overview shows recorded facts and links to raw messages/revisions, not a new engagement/mastery score.

## Material-library upgrade (stage 4, API 0.4.0)

The course library owns one canonical file and explicit session memberships select which files are available to each session. Upload adds to the library and current session; attach reuses the same file; removing a session link does not delete originals or affect other sessions. Title/visibility/extraction edits affect linked drafts, while published snapshots stay immutable. The additive schema4 migration preserves original materials provenance and learning rows; never remove its one-time backfill marker to refresh content.

New uploads and explicit teacher reprocess use local CPU OCR alongside native extraction. Supported standalone images: PNG/JPG/JPEG/WebP; Office/PDF formats remain available. CPU OCR recognizes text, not diagram relationships. The teacher UI exposes coverage, limited excerpts and review warnings. Resource limits:25MiB input,100MiB Office unpacked,200 native units,64 OCR attempts,16MP original images and approximately4MP OCR raster. Some Office presentation semantics remain unsupported; see extraction notes. Existing production materials are not automatically reprocessed or republished.

PDF preview opens an authenticated top-level tab instead of a sandboxed iframe. Student Enter sends, Shift+Enter inserts a newline, and IME confirmation does not send. Quiz has one structured question card; raw stored/exported transcripts stay unchanged.

## Guided-teaching upgrade

The stage-3 release upgrades the existing CT255 data in place; do **not** run fresh-install account/data bootstrap again. It adds `tutor_runs`, `tutor_requests` and message metadata without replacing old account, answer, course or immutable-version rows. Missing historical teaching profiles retain on-request reference delivery. New sessions default to comparison after a sufficient response, subject to the existing eligibility gate. Teaching drafts still need explicit course publication.

The student workspace is conversation-led; teacher configuration includes an editable teaching framework and server-compiled preview. Optional practice/reading is separate from required worksheet work and formal teacher confirmation. Transcript downloads use recorded messages and server timestamps, not model reconstructions.

The verified local `aicademiya-router` path uses JSON-schema-constrained guided responses. A premature answer-giving feedback may receive one bounded real-model wording revision; no demo fallback or fabricated progress is used. Existing legacy feedback and external-provider behavior remain separate. The shipped warm helper warms legacy feedback prefixes only; do not claim it prewarms the new guided protocol.

Follow the upgrade and restore-rehearsal sections below. Keep all old releases still referenced by persisted material snapshots. Configuration, model service and private data stay outside replaceable code.

## Release contents and integrity

`tools/build_v2_release.py` is stdlib-only and uses an explicit allowlist:

- **code archive**: `backend/aicademiya`, `backend/__init__.py`, current backend
  requirements, prebuilt `frontend/dist`, backup/warm/release-verification tools,
  new Linux launcher, these two V2 guides and the `runtime_v2` operator examples;
- **private_seed archive**: the clean EDUC7703 catalog, only its referenced
  student/teacher originals and question figures. It contains private teaching
  references and licensed material; share only with authorized operators.

No live DB/accounts, credentials, `.env`, local settings, learning history,
source tests, venv, node_modules, historical deployment guides or legacy runtime
namespace are packaged. The actual course identifiers `educ7703` / `EDUC7703`
are preserved. No compatibility module/cookie/environment aliases are supplied.
When adding runtime backend modules or compiled frontend chunks, update the
builder's explicit allowlist and release tests; do not broaden it to copy the
whole development tree. The packaged warm tool's development default is adapted
to `data-v2`; its source copy is unchanged.

Build locally using the project venv (or any Python 3.11+):

```sh
python tools/build_v2_release.py build --output-dir /private/new-release-output
python tools/build_v2_release.py verify --manifest /private/new-release-output/AIcademiya_V2-TAG.manifest.json
```

The build prints the exact code archive, seed archive, SHA256 file, manifest and
verification-report paths. Both archives have the same `AIcademiya_V2-TAG/` root.
The manifest records every file's safe relative path, component, bytes, SHA256
and mode; shell files are executable. A checksum is not a signature: obtain the
manifest, checksum file and standalone verifier through a trusted channel.
Keep both archives beside the manifest. The verifier checks exact membership,
hashes, modes, duplicate/path/link exclusions and both components **before**
extracting; it only writes a new directory and never overlays an installation.
Do not use unrestricted `tar -x` on an unverified handoff.

## Fresh Linux installation (manual, authorized operator only)

Use a supported Linux distribution with systemd and Python 3.11+; the CT255
target uses Debian13/Python3.13 with its matching `venv` package. Install OS Python/venv/pip,
CA certificates and any native libraries required by PyMuPDF/CPU ONNX/OCR.
Install backend dependencies into a **Linux-created** per-release venv; never
copy the Windows venv. No Node toolchain is required for the prebuilt frontend.
These commands assume root, a trusted incoming directory and no existing app:

```sh
umask 077
useradd --system --home-dir /var/lib/aicademiya --shell /usr/sbin/nologin aicademiya
install -d -m 0750 -o root -g aicademiya /opt/aicademiya /opt/aicademiya/releases
install -d -m 0700 -o aicademiya -g aicademiya /var/lib/aicademiya
install -d -m 0750 -o root -g aicademiya /etc/aicademiya
# Substitute the actual manifest/tag printed by the builder, not this example.
REV=AIcademiya_V2-TAG
cd /root/aicademiya-incoming
sha256sum -c "$REV.sha256"
# Standalone verifier must have been transferred through the trusted channel.
python3 /root/build_v2_release.py verify --manifest "$REV.manifest.json" \
  --extract-to /opt/aicademiya/new-install
mv "/opt/aicademiya/new-install/$REV" "/opt/aicademiya/releases/$REV"
ROOT="/opt/aicademiya/releases/$REV"
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
chown -R root:aicademiya "$ROOT"
chmod -R g+rX "$ROOT"
ln -s "releases/$REV" /opt/aicademiya/current
install -m 0640 -o root -g aicademiya "$ROOT/runtime_v2/aicademiya.conf.example" \
  /etc/aicademiya/aicademiya.conf
# Edit that private file locally. Do not print or export its values into logs.
install -m 0644 "$ROOT/runtime_v2/aicademiya.service" /etc/systemd/system/
```

The example explicitly binds `AICADEMIYA_HOST=192.168.32.55` and port `18773`,
uses `/var/lib/aicademiya`, disables demo authentication/search and leaves model
transport unconfigured. Allow the private listener only from authorized clients
or the verified proxy CT. Loopback binding is appropriate only for a reverse
proxy in the **same network namespace**, not one in another CT.

Create the initial administrator on the Linux console, with the intended
email/name. The CLI uses **masked local password and confirmation prompts**;
never pass a password in argv, a script, chat, environment or logs:

```sh
cd /opt/aicademiya/current
runuser -u aicademiya -- bash -c 'set -a; . /etc/aicademiya/aicademiya.conf; set +a; exec .venv/bin/python -m backend.aicademiya.manage_admin create --email admin@example.invalid --name "Site Administrator"'
# Replace the illustrative identity; no actual admin identity is prescribed.
```

New passwords require 8–512 characters with an ASCII letter and a digit.
`manage_admin create` imports the seed without demo accounts. The first local
administrator adopts only the still-unassigned seed course; existing teacher-
owned courses are never taken over, and later admins do not inherit its records.
Additional teachers can be provisioned with `python -m backend.aicademiya.create_teacher
--email ... --name ...` under the same private environment. Admin global
account/model permissions do not bypass course ownership. New initialized course
content is labelled `Initial edition`.

```sh
systemctl daemon-reload
systemctl enable --now aicademiya.service
curl --fail http://192.168.32.55:18773/api/health
curl --fail http://192.168.32.55:18773/api/bootstrap
journalctl -u aicademiya.service --since '10 minutes ago'
```

Expect health `status=ok`, bootstrap name `AIcademiya`, English locale and demo
false. Verify actual console-created login, role/ownership, course/question
figures and original downloads, plus uploads/imports in authorized acceptance.
Do not use `/api/auth/demo` in production. Browser cookie: `aicademiya_session`;
DB: `/var/lib/aicademiya/aicademiya.sqlite3`; module: `backend.aicademiya`.
Run **one worker**: startup pending-request recovery is not multi-worker-safe.
App initialization also runs schema migrations and scoped retention maintenance.

## Optional guest-local aicademiya-router proxy

Install this only when the owner authorizes use of the existing router at
`192.168.32.5:18280`. Do not restart, reconfigure or copy GPU models/KV. Confirm
that guest port `127.0.0.1:18280` is free, the target is reachable, and the
systemd executable exists at `/usr/lib/systemd/systemd-socket-proxyd` (adjust the
example path if the distribution uses another location).

```sh
ROOT=/opt/aicademiya/current
install -m 0644 "$ROOT/runtime_v2/aicademiya-model-proxy.socket" /etc/systemd/system/
install -m 0644 "$ROOT/runtime_v2/aicademiya-model-proxy.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aicademiya-model-proxy.socket
```

The socket activates its service and forwards **only guest loopback** to the
private GPU endpoint; it must not listen on `0.0.0.0`. Configure locally:
`AICADEMIYA_AI_PROVIDER=aicademiya-router`, `AICADEMIYA_AI_MODE=openai`,
`AICADEMIYA_AI_BASE_URL=http://127.0.0.1:18280/v1`,
`AICADEMIYA_AI_MODEL=AIcademiya-64kx3-Qwen3.8-27B`. The exact loopback URL/model gate enables
server-derived teaching scope and the 600s timeout; a direct LAN URL is not an
equivalent substitute. Saved DB model settings override environment defaults.
Restart only the application after changes. HTTP health/bootstrap is not model
proof; a bounded real-model test needs separate authorization and resource checks.

Optional warmer: `python tools/warm_aicademiya_prefix.py --db /var/lib/aicademiya/aicademiya.sqlite3`
is list-only. `--session ID --question ID --workers v100` makes one real warm
request; never run automatically. It reads published static prefixes, not
student history. Warm HTTP success alone is not proof of a cache hit.

For later HTTPS ingress, set `AICADEMIYA_COOKIE_SECURE=true`, exact HTTPS
`AICADEMIYA_ALLOWED_ORIGINS` and the verified reverse-proxy IP in
`AICADEMIYA_FORWARDED_ALLOW_IPS`. Use long enough proxy timeouts for the router.
No ingress change or public exposure is performed by this release.

## Normal future upgrades: keep CT255

1. Stage and verify a new code **and seed** release under
   `/opt/aicademiya/releases/AIcademiya_V2-NEW/`; create its own Linux venv. Keep
   configuration under `/etc/aicademiya` and data under `/var/lib/aicademiya`.
2. Take/validate a consistent data backup; rehearse the new code/schema against
   a restored isolated copy with model/search disabled. Check dependency/OS,
   schema and data compatibility, file permissions, disk space and RAM.
3. Stop application writes briefly, take a final backup, then switch
   `/opt/aicademiya/current` to the new release and restart the one-worker service.
   Startup performs the tested migrations. Read back health, authenticated
   workflows and resource downloads before accepting the upgrade.
4. The catalog imports **once**. A new seed/catalog does not replace an existing
   course. Existing DB/snapshot paths may still point into older release seeds:
   retain all referenced release directories, or use validated backup/restore
   relocation before retiring them. Static figures also require the matching
   catalog/assets, including figures used by historical editions.
5. Roll back a **compatible code/data pair**. Repointing old code alone after an
   incompatible schema migration is unsafe; stop writes and restore the matching
   pre-upgrade backup to a new data directory. See `BACKUP-RESTORE-V2.md`.

A new CT is not required for ordinary code upgrades. Major OS replacement or
explicit blue/green migration is a separate decision. No automated deployment,
retirement, destructive cleanup or credential collection is part of this bundle.
