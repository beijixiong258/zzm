# AIcademiya_V2 backup and restore

`tools/backup_data.py` is a stdlib-only local CLI. It does not start the app,
contact AI/search, migrate an old site or collect credentials. Treat backups as
private: they contain account hashes, learning/history, model/search settings and the
installation scope secret. Use restrictive storage and encrypted off-host copies
under an independently authorized procedure; a same-host copy is not disaster
recovery proof.

## What V2 captures

- `aicademiya.sqlite3` via SQLite's backup API (committed WAL included), switched
  to self-contained DELETE journaling in the copy; all table rows and schema.
- All `uploads/` files, including pending imports, plus every referenced external
  original/asset directory under the explicitly permitted `--materials-root`.
- Exact path bindings by table/row/JSON position in **current materials,
  immutable `course_versions.snapshot_json`, and worksheet
  `import_staging.payload_json`**. One material ID can refer to different files
  in different editions; directories with no figures are preserved too.
- `manifest.json` version 2 with SHA256/size, table counts/fingerprints, exact
  path bindings and directories. Missing/unbacked historical/staging files fail
  the operation rather than being silently dropped.

It does **not** capture app code/venv/frontend, sample catalog/static question
assets, `/etc/aicademiya` config/credentials, systemd/network configuration or
rebuildable GPU KV/models. Retain the matching verified code and private-seed
archives separately; protect a separate copy of private configuration using the
operator's approved secret-backup method. Do not put that configuration into a
runtime release archive.

## Complete document revisions in schema9

SQLite captures immutable normalized manifests, operational jobs and source-review
receipts. All parse rasters, crops, raw evidence and recovery records below uploads/
are captured, including old revisions still referenced by published editions. The
exact path visitor also relocates private document_dir bindings in current material
JSON and every immutable snapshot; it does not rewrite arbitrary literal strings.
Original/derived paths must resolve after restore with old source directories absent.

Stop/drain application writes and its owned processing job before the consistent
operational backup; a DB snapshot is not a transaction across a still-writing parser.
A restored queued job whose source/path identity changed fails safely and needs a
new explicit request; do not automatically run an old request in a relocated namespace.
Never overwrite an existing restore target or roll back schema9 solely by changing
the code symlink. Match code, restored data and compatible private configuration.

Remote CPU model/runtime files and the document-worker SSH identity/known-hosts are
separate infrastructure, not included in this document-data backup. In particular,
worker-ssh/ beside uploads/ is not an uploads asset directory. Protect its private
key/config separately or reprovision a restricted worker key; never put it in a code
release, browser storage or public test artifact.

## Avatar and feedback in schema7

The complete SQLite snapshot includes normalized PNG BLOBs in account_avatars and
feedback text/status/human reply/revision. The manifest inventory encodes bytes as
hex for exact comparison; no new filesystem binding is needed. Restore verifies
these bytes with the same all-table integrity and schema checks. Validate authenticated
avatar image/me and own/admin feedback readback after isolated startup/restart,
including stale revision protection. Old accounts have no synthetic avatar/feedback.
Global user purge removes their avatar by CASCADE and anonymizes feedback author by
SET NULL, preserving submitted text. Do not silently restore expired identities or
change archived-account deadlines. Backups now also contain chosen profile images
and user feedback; keep them private alongside existing learning and credential data.

## Course trash in schema6

Course trash is an additive operational table, not file deletion. The complete
SQLite backup/restore includes its course ID, timestamp and actor, plus all course
content and historical references. A restored course marker must still block access
until an authorized explicit restore; initialization must not silently untrash it.
No new external path binding is introduced by this table. Preserve independent
account/enrollment retention deadlines; a course restore does not renew them.

## Consistent backup

The SQLite snapshot is transaction-consistent, but mutable upload bytes and DB
references are not a single filesystem transaction. Stop application writes for
an operational backup/upgrade; the tool checks copied source bytes but a live
multi-file editing race can still prevent a complete snapshot. Commands below
are manual examples, with a **new, non-existing destination**:

```sh
umask 077
install -d -m 0700 /srv/aicademiya-backups
systemctl stop aicademiya.service
/opt/aicademiya/current/.venv/bin/python /opt/aicademiya/current/tools/backup_data.py backup \
  --data-dir /var/lib/aicademiya \
  --materials-root /opt/aicademiya/releases \
  --destination /srv/aicademiya-backups/pre-upgrade-UNIQUE
# Restart only after successful completion, or resolve failure privately.
systemctl start aicademiya.service
```

The allowed releases root covers seed originals still referenced from older
releases; only referenced external files/directories are copied, not every code
file. Data-dir must contain `aicademiya.sqlite3`. No symlinks are supported.
Destination must be new and outside the source data directory. Parent storage
must already exist. Success prints JSON with `integrity: "ok"`, table counts and
file count; these are not proof of boot/HTTP recovery.

There is no standalone `verify` subcommand. `restore` validates the backup
manifest, files, SQLite integrity/foreign keys and all records before restoring.
A failure leaves the source unchanged and retains any newly created incomplete
private destination; do not treat that directory as a successful backup.

## Restore rehearsal or recovery

Stop writes before a recovery. Never overwrite the running data directory.
`restore` requires a new destination **outside the backup directory**:

```sh
/opt/aicademiya/current/.venv/bin/python /opt/aicademiya/current/tools/backup_data.py restore \
  --source /srv/aicademiya-backups/pre-upgrade-UNIQUE \
  --destination /var/lib/aicademiya-restored-UNIQUE
```

The tool relocates every bound path into the new root, verifies full normalized
records, exact schema/triggers and original/figure bytes. Its immutable-edition
UPDATE trigger is temporarily suspended only inside the new-copy relocation
transaction, then restored exactly. Expected success JSON:
`integrity: "ok"`, `records_match: true`, `files_match: true`, plus counts.
The restored database itself has rewritten paths, so its raw SHA256 differs
from the original snapshot; unchanged resource file hashes must still match.

Before accepting a restore, check:

1. Available disk/inodes for the backup, restored copy and retained release;
   memory for app/OCR, compatible Python/dependencies/schema and resource owner/
   mode. Give the service user access to all restored files. Private resource
   paths in JSON are evidence: verify they resolve **inside the restored root**,
   not against an accidentally still-present source tree.
2. Current original downloads and asset/figure endpoints; historical immutable
   edition downloads/worksheet figures; pending worksheet import previews and
   confirmation. Check empty asset directories, removed-session history and
   references that differ between editions. Do not normalize away records merely
   to make counts/hashes agree. Static `/api/assets/...` diagrams require the
   matching private-seed catalog/assets outside this data backup.
3. Boot an isolated copy with `AICADEMIYA_DATA_DIR` pointing to the restore and a
   separate listener. Disable model/search in both the environment and any
   saved DB provider settings. **Saved DB model and search settings override environment**;
   change settings only in the disposable synthetic/restored rehearsal copy.
   A restored scope secret duplicates production's namespace: never send
   independent real model/warm requests from that clone to production caches.
4. Verify health/bootstrap, authentication/roles, owned courses, learning/history
   and the resource operations above. Startup runs migrations and scoped
   retention maintenance: test with a disposable copy, not the backup itself.
   Preserve the original backup for a later recovery with the matching release.

For the supplied systemd unit, the writable path is `/var/lib/aicademiya`.
If production recovery selects a new sibling data root, set that absolute root
in `/etc/aicademiya/aicademiya.conf` **and** change `ReadWritePaths` via a private
systemd drop-in to the same root; run `daemon-reload`, then restart/read back the
exact service. Preserve the old data directory and release until acceptance.
Do not merely change the env while leaving the filesystem sandbox pointed at
the old root.

## Guided-teaching state

Stage-3 guided runs, request identities, optional generated items/keys, original learner responses and message metadata are ordinary SQLite state and are included in the all-table backup. They do not introduce new filesystem binding locations. A restore rehearsal must preserve their records and request IDs, not merely the visible worksheet answer count. Keep model/search disabled for restored production copies because the installation cache scope secret is duplicated.

## Course material memberships (stage 4)

Schema4 includes `material_courses` and `session_materials`, indexes/triggers, and the one-time `meta.stage4_material_library` marker. These are included in the all-table/schema backup and introduce no new filesystem paths. `materials.session_id` is retained origin provenance, not current membership. Restore rehearsals must verify shared/unassigned library originals and historical material/figure access after source paths are made unavailable. Do not drop the marker or run older code that treats provenance as the session membership authority.

## Teacher-preview bindings (stage 6)

Schema5 adds teacher_previews with owner/session ID, preview ID, saved revision and binding timestamp. All-table/schema backup includes it; it adds no filesystem path locations. Revision identity excludes absolute original/asset paths so a relocated restored copy is not falsely stale. Verify bound/current revisions after recovery; never auto-reset or bind historical teacher tests during migration. Restore copies must still disable model/search and never use production's duplicated cache namespace for inference.

## Compatibility and upgrades

Manifest V1 is accepted only when all current/historical/staging paths can be
bound unambiguously to resources actually saved in that archive. Absent old
historical originals cannot be reconstructed. This compatibility is for backup
formats of the current `aicademiya.sqlite3` runtime, **not** an alias/importer for
old application namespaces or permission to migrate CT254 accounts.

Ordinary releases remain in CT255. Pair the tested code/schema with a validated
pre-upgrade backup, stage dependencies, stop writes for final backup, switch the
current code link and verify migration/recovery. After an incompatible migration,
rollback requires the matching old code **and** restored pre-upgrade data.
See `RUNTIME_V2.md` for fresh installation, the masked local admin CLI and the
conditional loopback proxy. No remote service/data changes are automated here.
