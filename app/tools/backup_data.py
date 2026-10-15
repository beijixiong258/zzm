"""Private SQLite snapshot + material files; stdlib only, no app/AI startup."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from contextlib import closing, contextmanager

DB_NAME = "aicademiya.sqlite3"


@contextmanager
def readonly(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        conn.execute("PRAGMA query_only=ON")
        yield conn
    finally:
        conn.close()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_dir(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("Destination must be a new directory")
    path.mkdir(mode=0o700, parents=False)
    return path.resolve()


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or any(p.is_symlink() for p in path.parents):
        raise ValueError("Material must be a regular file without symlinks")
    return path.resolve()


def copy_private(source, target):
    source = regular(source)
    before = digest(source)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with source.open("rb") as src, target.open("xb") as dst:
        os.chmod(target, 0o600)
        shutil.copyfileobj(src, dst)
    if digest(target) != before or digest(source) != before:
        raise ValueError("Source material changed during backup")


def safe_member(root, name):
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or not relative.parts:
        raise ValueError("Invalid manifest path")
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Invalid manifest path")
    return target


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def path_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def map_record_paths(table, columns, row, remap):
    """Visit only schema-owned paths, including JSON encoded inside snapshots.

    A material ID is not a file identity: two editions can retain different
    originals/assets for that same ID. Bind each exact record/JSON location.
    """
    row = list(row)
    if table not in ("materials", "course_versions", "import_staging"):
        return row
    identifier = row[columns.index("id")]

    def relocate(value, column, path, kind, assets=None):
        if not value:
            return value
        key = json_text([table, identifier, column, path])
        return remap(key, value, kind, assets)

    def metadata(raw, column, path):
        if raw.get("assets_dir"):
            raw["assets_dir"] = relocate(raw["assets_dir"], column, path + ["assets_dir"], "directory", raw.get("assets", []))
        if raw.get("document_dir"):
            # Schema-owned directory, not arbitrary strings inside source text
            # or immutable relative manifests. Retain raw/raster/crop files.
            raw["document_dir"] = relocate(raw["document_dir"], column, path + ["document_dir"], "directory")
        return raw

    if table == "materials":
        if "file_path" in columns:
            i = columns.index("file_path")
            row[i] = relocate(row[i], "file_path", [], "file")
        if "content_json" in columns:
            i = columns.index("content_json")
            raw = json.loads(row[i])
            if raw.get("assets_dir") or raw.get("document_dir"):
                row[i] = json_text(metadata(raw, "content_json", []))
    elif table == "course_versions":
        i = columns.index("snapshot_json")
        raw = json.loads(row[i])
        for si, session in enumerate(raw["sessions"]):
            for mi, material in enumerate(session.get("_materials", [])):
                base = ["sessions", si, "_materials", mi]
                if material.get("file_path"):
                    material["file_path"] = relocate(material["file_path"], "snapshot_json", base + ["file_path"], "file")
                info = json.loads(material["content_json"])
                if info.get("assets_dir") or info.get("document_dir"):
                    material["content_json"] = json_text(metadata(info, "snapshot_json", base + ["content_json"]))
        row[i] = json_text(raw)
    elif row[columns.index("kind")] == "worksheet":
        i = columns.index("payload_json")
        raw = json.loads(row[i])
        raw["file_path"] = relocate(raw["file_path"], "payload_json", ["file_path"], "file")
        metadata(raw["material"], "payload_json", ["material"])
        row[i] = json_text(raw)
    return row


def visit_database(path, remap):
    with readonly(path) as conn:
        for table in ("materials", "course_versions", "import_staging"):
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            cursor = conn.execute('SELECT * FROM "' + table + '"')
            columns = [c[0] for c in cursor.description]
            for row in cursor:
                map_record_paths(table, columns, row, remap)


def verify_asset_members(relative, assets, files):
    for asset in assets or []:
        key = asset["key"]
        # Apply the same containment rule to extracted figure names.
        safe_member(Path("."), key)
        if relative + "/" + key not in files:
            raise ValueError("Unbacked worksheet asset")


def path_normalizer(path_bindings, target=None):
    used = set()

    def remap(key, value, kind, assets):
        binding = path_bindings.get(key)
        if not binding or binding["kind"] != kind:
            raise ValueError("Unbacked path record")
        relative = binding["relative"]
        expected = str(target / relative) if target is not None else None
        if (target is not None and value != expected) or (target is None and path_digest(value) != binding["source_sha256"]):
            raise ValueError("Path record verification failed")
        used.add(key)
        return relative

    return remap, used


def inspect_database(path, bindings, path_bindings=None, target=None):
    remap, used = path_normalizer(path_bindings, target) if path_bindings is not None else (None, None)
    with readonly(path) as conn:
        if [r[0] for r in conn.execute("PRAGMA integrity_check")] != ["ok"]:
            raise ValueError("SQLite integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("SQLite foreign key check failed")
        tables = {}
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for name in names:
            quoted = '"' + name.replace('"', '""') + '"'
            cursor = conn.execute("SELECT * FROM " + quoted)
            columns = [c[0] for c in cursor.description]
            rows = []
            for row in cursor:
                row = list(row)
                if remap is not None:
                    row = map_record_paths(name, columns, row, remap)
                elif name == "materials" and "file_path" in columns:
                    mid = row[columns.index("id")]
                    file_index = columns.index("file_path")
                    if row[file_index]:
                        if mid not in bindings:
                            raise ValueError("Unbacked material record")
                        row[file_index] = bindings[mid]
                # SQLite app schema stores text/numbers; bytes supported for future additions.
                row = [{"bytes_hex": v.hex()} if isinstance(v, bytes) else v for v in row]
                rows.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            payload = json.dumps(sorted(rows), ensure_ascii=False, separators=(",", ":")).encode()
            tables[name] = {"count": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}
        if used is not None and used != set(path_bindings):
            raise ValueError("Path binding record missing")
        return tables


def backup(data_dir, destination, materials_root=None):
    data_dir = Path(data_dir).resolve()
    db = regular(data_dir / DB_NAME)
    uploads = data_dir / "uploads"
    if uploads.is_symlink():
        raise ValueError("Uploads directory cannot be a symlink")
    destination = Path(destination).absolute()
    if destination.resolve().is_relative_to(data_dir):
        raise ValueError("Backup must be outside the source data directory")
    allowed = Path(materials_root).resolve() if materials_root else None
    target = private_dir(destination)
    snapshot = target / DB_NAME
    # File permissions are set before SQLite writes secrets into it.
    snapshot.touch(mode=0o600, exist_ok=False)
    with readonly(db) as src, closing(sqlite3.connect(snapshot)) as dst:
        src.backup(dst, pages=256, sleep=0.05)
        # Snapshot is self-contained; do not retain copied WAL mode/sidecars.
        dst.execute("PRAGMA journal_mode=DELETE")
    bindings = {}
    sources, directories, path_bindings = {}, {"uploads"}, {}
    if uploads.exists():
        for source in sorted(uploads.rglob("*")):
            if source.is_symlink():
                raise ValueError("Symlinks in uploads are not supported")
            if source.is_file():
                relative = "uploads/" + source.relative_to(uploads).as_posix()
                sources[relative] = source
            elif source.is_dir():
                directories.add("uploads/" + source.relative_to(uploads).as_posix())
    (target / "uploads").mkdir(mode=0o700)
    def register(key, value, kind, assets):
        source = Path(value)
        if kind == "file":
            source = regular(source)
        elif source.is_symlink() or not source.is_dir() or any(p.is_symlink() for p in source.parents):
            raise ValueError("Asset directory must be a regular directory without symlinks")
        else:
            source = source.resolve()
        if source.is_relative_to(uploads):
            relative = "uploads/" + source.relative_to(uploads).as_posix()
        elif allowed and source.is_relative_to(allowed):
            relative = "materials/" + source.relative_to(allowed).as_posix()
        else:
            raise ValueError("External material requires an explicit permitted --materials-root")
        path_bindings[key] = {"relative": relative, "kind": kind, "source_sha256": path_digest(value)}
        table, mid, column, location = json.loads(key)
        if table == "materials" and column == "file_path":
            bindings[mid] = relative
        if kind == "file":
            sources[relative] = source
        else:
            directories.add(relative)
            for member in sorted(source.rglob("*")):
                if member.is_symlink():
                    raise ValueError("Symlinks in asset directories are not supported")
                name = relative + "/" + member.relative_to(source).as_posix()
                if member.is_file():
                    sources[name] = regular(member)
                elif member.is_dir():
                    directories.add(name)
            verify_asset_members(relative, assets, sources)
        return relative

    visit_database(snapshot, register)
    for relative in sorted(directories):
        safe_member(target, relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    for relative, source in sorted(sources.items()):
        copy_private(source, safe_member(target, relative))
    # Recheck all referenced source bytes after the complete copy batch.
    for relative, source in sources.items():
        if digest(source) != digest(target / relative):
            raise ValueError("Source material changed during backup")
    tables = inspect_database(snapshot, bindings, path_bindings)
    files = {p.relative_to(target).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p)}
             for p in sorted(target.rglob("*")) if p.is_file()}
    manifest = {"version": 2, "created_at": datetime.now(timezone.utc).isoformat(),
                "database": DB_NAME, "integrity": "ok", "tables": tables,
                "files": files, "material_bindings": bindings,
                "path_bindings": path_bindings, "directories": sorted(directories)}
    manifest_path = target / "manifest.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        os.chmod(manifest_path, 0o600)
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"mode": "backup", "path": str(target), "integrity": "ok",
            "table_counts": {k: v["count"] for k, v in tables.items()}, "file_count": len(files)}


def portable_path(value):
    """Read old path syntax without relying on the restore host's OS."""
    return PureWindowsPath(value) if PureWindowsPath(value).drive or "\\" in value else PurePosixPath(value)


def legacy_path_bindings(source, manifest):
    """V1 omitted JSON paths; recover only references whose files were saved.

    Infer external roots from its live material bindings, and recognize the
    stage2 default uploads subtree. Never read missing files from the old host.
    An omitted historical external original cannot be recovered: fail closed.
    """
    files = manifest["files"]
    directories = {"uploads"}
    for name in files:
        directories.update(p.as_posix() for p in PurePosixPath(name).parents if p.as_posix() != ".")
    roots = set()
    with readonly(source / DB_NAME) as conn:
        for mid, value in conn.execute("SELECT id,file_path FROM materials WHERE file_path IS NOT NULL AND file_path != ''"):
            relative = manifest["material_bindings"][mid]
            old = portable_path(value)
            tail = PurePosixPath(relative).parts[1:]
            root = old.parents[len(tail) - 1]
            if root.joinpath(*tail) != old:
                raise ValueError("Invalid legacy material binding")
            roots.add((root, relative.split("/", 1)[0]))

    bindings = {}

    def register(key, value, kind, assets):
        old = portable_path(value)
        candidates = set()
        for root, namespace in roots:
            if type(old) is type(root) and old.is_relative_to(root):
                candidates.add(namespace + "/" + old.relative_to(root).as_posix())
        for i, part in enumerate(old.parts[:-1]):
            if part.lower() == "uploads":
                candidates.add("uploads/" + "/".join(old.parts[i + 1:]))
        valid = set()
        for relative in candidates:
            safe_member(source, relative)
            if kind == "file" and relative in files:
                valid.add(relative)
            elif kind == "directory" and (relative in directories or (relative.startswith(("uploads/", "materials/")) and not assets)):
                valid.add(relative)
        if len(valid) != 1:
            raise ValueError("Legacy backup lacks an unambiguous saved path")
        relative = valid.pop()
        if kind == "directory":
            directories.add(relative)
            verify_asset_members(relative, assets, files)
        bindings[key] = {"relative": relative, "kind": kind, "source_sha256": path_digest(value)}
        return relative

    visit_database(source / DB_NAME, register)
    return bindings, sorted(directories)


def validate_backup(source):
    source = Path(source).resolve()
    manifest = json.loads(regular(source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") not in (1, 2) or manifest.get("database") != DB_NAME:
        raise ValueError("Unsupported backup manifest")
    if DB_NAME not in manifest["files"]:
        raise ValueError("Database missing from manifest")
    for name, info in manifest["files"].items():
        path = regular(safe_member(source, name))
        if path.stat().st_size != info["bytes"] or digest(path) != info["sha256"]:
            raise ValueError("Backup file verification failed")
    for relative in manifest["material_bindings"].values():
        if relative not in manifest["files"] or not relative.startswith(("uploads/", "materials/")):
            raise ValueError("Invalid material binding")
    if manifest["version"] == 1:
        if inspect_database(source / DB_NAME, manifest["material_bindings"]) != manifest["tables"]:
            raise ValueError("Backup record verification failed")
        manifest["path_bindings"], manifest["directories"] = legacy_path_bindings(source, manifest)
        # This new full normalization, not V1's live-only fingerprint, is the
        # baseline used to verify the relocated restore.
        manifest["normalized_tables"] = inspect_database(source / DB_NAME, {}, manifest["path_bindings"])
    else:
        for name in manifest["directories"]:
            path = safe_member(source, name)
            if not name.startswith(("uploads/", "materials/")) and name not in ("uploads", "materials"):
                raise ValueError("Invalid asset directory binding")
            if path.is_symlink() or not path.is_dir() or any(p.is_symlink() for p in path.parents):
                raise ValueError("Asset directory verification failed")
        for binding in manifest["path_bindings"].values():
            relative = binding["relative"]
            safe_member(source, relative)
            if not relative.startswith(("uploads/", "materials/")):
                raise ValueError("Invalid path binding")
            if binding["kind"] == "file":
                if relative not in manifest["files"]:
                    raise ValueError("Unbacked material record")
            elif binding["kind"] != "directory" or relative not in manifest["directories"]:
                raise ValueError("Unbacked asset directory")
        remap, _ = path_normalizer(manifest["path_bindings"])
        def check_assets(key, value, kind, assets):
            relative = remap(key, value, kind, assets)
            if kind == "directory":
                verify_asset_members(relative, assets, manifest["files"])
            return relative
        visit_database(source / DB_NAME, check_assets)
        if inspect_database(source / DB_NAME, {}, manifest["path_bindings"]) != manifest["tables"]:
            raise ValueError("Backup record verification failed")
        manifest["normalized_tables"] = manifest["tables"]
    return manifest


def restore(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    if destination.resolve().is_relative_to(source):
        raise ValueError("Restore must be outside the backup directory")
    manifest = validate_backup(source)
    target = private_dir(destination)
    for relative in manifest["directories"]:
        safe_member(target, relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    for relative in manifest["files"]:
        copy_private(safe_member(source, relative), safe_member(target, relative))
    (target / "uploads").mkdir(exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(target / DB_NAME)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        # Offline relocation is not curriculum editing. Temporarily suspend
        # only stage2's UPDATE guard inside this new copy's transaction; restore
        # its exact SQL before commit (rollback also restores it on failure).
        guard = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='immutable_version_update' AND tbl_name='course_versions'").fetchone()
        if guard:
            conn.execute("DROP TRIGGER immutable_version_update")
        normalize, _ = path_normalizer(manifest["path_bindings"])
        def relocate(key, value, kind, assets):
            return str(target / normalize(key, value, kind, assets))
        for table in ("materials", "course_versions", "import_staging"):
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            cursor = conn.execute('SELECT * FROM "' + table + '"')
            columns = [c[0] for c in cursor.description]
            for row in cursor.fetchall():
                updated = map_record_paths(table, columns, row, relocate)
                changes = [(c, v) for c, v, old in zip(columns, updated, row) if v != old]
                if changes:
                    fields = ",".join('"' + c + '"=?' for c, _ in changes)
                    conn.execute('UPDATE "' + table + '" SET ' + fields + ' WHERE id=?',
                                 [v for _, v in changes] + [row[columns.index("id")]])
        if guard:
            conn.execute(guard[0])
    with readonly(source / DB_NAME) as original, readonly(target / DB_NAME) as restored:
        schema = "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        if original.execute(schema).fetchall() != restored.execute(schema).fetchall():
            raise ValueError("Restored schema verification failed")
    if inspect_database(target / DB_NAME, {}, manifest["path_bindings"], target) != manifest["normalized_tables"]:
        raise ValueError("Restored record verification failed")
    for relative, info in manifest["files"].items():
        if relative != DB_NAME and digest(target / relative) != info["sha256"]:
            raise ValueError("Restored material verification failed")
    return {"mode": "restore", "path": str(target), "integrity": "ok", "records_match": True,
            "files_match": True, "table_counts": {k: v["count"] for k, v in manifest["tables"].items()},
            "file_count": len(manifest["files"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    b = commands.add_parser("backup")
    b.add_argument("--data-dir", type=Path, required=True)
    b.add_argument("--destination", type=Path, required=True)
    b.add_argument("--materials-root", type=Path)
    r = commands.add_parser("restore")
    r.add_argument("--source", type=Path, required=True)
    r.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.mode == "backup":
            result = backup(args.data_dir, args.destination, args.materials_root)
        else:
            result = restore(args.source, args.destination)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        # Paths/errors can embed private records. Never print DB values or raw exceptions.
        print("Backup/restore failed; existing source is unchanged. Any new incomplete destination is retained privately.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
