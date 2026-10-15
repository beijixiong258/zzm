#!/usr/bin/env python3
"""Build/verify a private AIcademiya_V2 code release and separate curriculum seed.

Stdlib only. No app imports, data initialization, credentials or network calls.
A manifest is integrity evidence, not a signature: obtain it through a trusted
channel. The private seed contains copyrighted/teacher-only teaching material.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tarfile

IDENTITY = "AIcademiya_V2"
APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MODULES = (
    "__init__", "ai", "authoring", "create_teacher", "db", "learning_routes",
    "link_materials", "main", "manage_admin", "materials", "material_library", "material_extraction", "migrations", "models",
    "roster", "services", "versions", "version_context", "web_search", "worksheet_import",
    "guided_routes", "guided_engine", "guided_director", "guided_state", "guided_migration", "teaching",
    "teacher_preview", "evidence", "source_review", "teacher_workbench_routes", "service_settings", "course_lifecycle",
    "account_avatars", "feedback", "account_features_migration",
    "auth", "config", "access_control", "http_security", "material_security", "extraction_limits",
    "course_staff", "global_accounts", "account_import",
    "document_api", "document_bundle", "document_jobs", "document_storage", "document_supplements", "reading_context", "guided_reading", "visual_context", "session_lifecycle", "model_connection", "worksheet_materials",
)
FRONTEND_ROOT = {
    "index.html", "aicademiya-mark.svg", "aicademiya-mark-small.svg", "aicademiya-mark-light.svg", "apple-touch-icon.png", "favicon-32.png",
    "favicon-48.png", "favicon.ico", "favicon.svg", "roster-template.csv",
}
RUNTIME_FILES = (
    "aicademiya.conf.example", "start-linux.sh", "aicademiya.service",
    "aicademiya-model-proxy.socket", "aicademiya-model-proxy.service",
)
FORBIDDEN_PARTS = {
    ".env", "node_modules", ".venv", "venv", "__pycache__", "tests", "history",
    "data", "data-v2", "uploads", "local-settings.json", "local-settings-v2.json",
    "educ7703", "akademiya", ".git", ".pytest_cache",
}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pyc", ".pyo", ".pem", ".key"}


def safe_path(name):
    """Reject paths ambiguous across Linux and Windows; never normalize them."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Unsafe relative path")
    p = PurePosixPath(name)
    if p.is_absolute() or PureWindowsPath(name).drive or any(x in ("", ".", "..") for x in name.split("/")):
        raise ValueError("Unsafe relative path")
    return p


def permitted_name(name):
    p = safe_path(name)
    if any(x.lower() in FORBIDDEN_PARTS or x.lower().startswith(".env.") for x in p.parts):
        raise ValueError("Forbidden runtime path")
    if p.suffix.lower() in FORBIDDEN_SUFFIXES or name.endswith(("-wal", "-shm")):
        raise ValueError("Forbidden runtime file")
    return p


def regular(root, name):
    p = root.joinpath(*safe_path(name).parts)
    if p.is_symlink() or any(x.is_symlink() for x in p.parents) or not p.is_file():
        raise ValueError("Release inputs must be existing regular non-symlink files")
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError("Release input escapes source root")
    return p


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(source):
    """An explicit code allowlist plus only catalog-bound seed resources."""
    source = Path(source).resolve()
    files = {}

    def add(destination, origin=None, component="code"):
        permitted_name(destination)
        data = regular(source, origin or destination).read_bytes()
        mode = 0o755 if destination.endswith(".sh") else (0o600 if component == "private_seed" else 0o644)
        files[destination] = {"data": data, "component": component, "mode": mode}

    add("backend/__init__.py")
    add("backend/requirements.txt")
    for module in BACKEND_MODULES:
        add("backend/aicademiya/" + module + ".py")
    for name in sorted(FRONTEND_ROOT):
        add("frontend/dist/" + name)
    assets = source / "frontend/dist/assets"
    if not assets.is_dir() or assets.is_symlink():
        raise ValueError("Prebuilt frontend assets are missing")
    chunk_pattern = r"(?:index|AdminAccounts|LearningHistory|ModelSettings|Profile|Roster|TeacherSession|Versions|SettingsWorkspace|Feedback|CourseLibrary|CourseTrash|CourseStudents|account-management|refresh-cw)-[A-Za-z0-9_-]{8}\.(js|css)"
    for path in sorted(assets.iterdir()):
        if re.fullmatch(chunk_pattern, path.name):
            add("frontend/dist/assets/" + path.name)
        elif re.fullmatch(r"[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8}\.(js|css)", path.name):
            raise ValueError("New frontend chunk requires an explicit runtime allowlist update")
    for tool in ("backup_data.py", "warm_aicademiya_prefix.py", "build_v2_release.py"):
        add("tools/" + tool)
    for tool in ("document_ssh_bridge.py", "document_worker_service.py", "parser_worker.py", "parser_helpers.py", "gpu_lease.py", "page_vision_runtime.py"):
        add("tools/document_stage12/" + tool)
    for tool in ("parse_material.py", "office_inventory.py", "archive_guard.py", "prepared_material.py", "simple_material.py", "source_text.py", "ocr_verification.py"):
        add("tools/material_stage13/" + tool)
    for tool in ("__init__.py", "adapter.py", "prepared.py", "provenance.py", "page_worker.py"):
        add("tools/material_stage15/" + tool)
    for tool in ("workbook_inventory.py", "workbook_material.py", "legacy_office.py", "workbook_supplements.py"):
        add("tools/material_stage16/" + tool)
    # Fix only the copied warm tool's obsolete development data default. The
    # original tool is deliberately outside this builder's write authority.
    warm = files["tools/warm_aicademiya_prefix.py"]["data"]
    files["tools/warm_aicademiya_prefix.py"]["data"] = warm.replace(b'str(APP / "data")', b'str(APP / "data-v2")')
    # The new launcher deliberately replaces the historical host-loopback copy.
    add("tools/start-linux.sh", "runtime_v2/start-linux.sh")
    for name in RUNTIME_FILES:
        add("runtime_v2/" + name)
    for name in ("RUNTIME_V2.md", "BACKUP-RESTORE-V2.md"):
        add(name)

    catalog = json.loads(regular(source, "sample_data/catalog.json").read_text(encoding="utf-8-sig"))
    if set(catalog) != {"schema_version", "course", "sessions"} or catalog["schema_version"] != 1:
        raise ValueError("Unsupported clean sample catalog")
    if catalog["course"]["code"] != "EDUC7703" or catalog["course"]["id"] != "educ7703":
        raise ValueError("Preserve the actual EDUC7703 course identity")
    add("sample_data/catalog.json", component="private_seed")
    for session in catalog["sessions"]:
        for material in session.get("materials", []):
            if material.get("assets_dir"):
                raise ValueError("Seed catalog must not contain absolute asset-directory state")
            if material.get("file_path"):
                name = material["file_path"]
                p = safe_path(name)
                if len(p.parts) < 3 or p.parts[:2] not in (("materials", "student"), ("materials", "teacher")):
                    raise ValueError("Seed originals must be under clean student/teacher materials")
                if p.suffix.lower() not in {".txt", ".md", ".pdf", ".docx", ".pptx"}:
                    raise ValueError("Unsupported seed original")
                add("sample_data/" + name, component="private_seed")
        for question in session.get("questions", []):
            for image in question.get("images", []):
                url = image["url"]
                if not url.startswith("/api/assets/"):
                    raise ValueError("Seed figures must use package-local static assets")
                name = url[len("/api/assets/"):]
                if safe_path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                    raise ValueError("Unsupported seed figure")
                add("sample_data/assets/" + name, component="private_seed")
    return files


def write_archive(path, release, files, component):
    # Stable gzip/tar metadata. Source content, not host paths, enters the archive.
    with Path(path).open("xb") as raw:
        os.chmod(path, 0o600)
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, item in sorted(files.items()):
                    if item["component"] != component:
                        continue
                    info = tarfile.TarInfo(release + "/" + name)
                    info.size = len(item["data"])
                    info.mode = item["mode"]
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(item["data"]))


def verify(manifest_path, extract_to=None):
    """Verify BOTH archives before optionally writing a new extraction directory."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("identity") != IDENTITY:
        raise ValueError("Unsupported release manifest")
    release = manifest["release"]
    if not re.fullmatch(r"AIcademiya_V2-[A-Za-z0-9][A-Za-z0-9._-]*", release):
        raise ValueError("Unsafe release identifier")
    expected = manifest["files"]
    for name, info in expected.items():
        permitted_name(name)
        if info["component"] not in {"code", "private_seed"} or info["mode"] not in (0o600, 0o644, 0o755):
            raise ValueError("Invalid manifest file entry")
    if set(manifest["archives"]) != {"code", "private_seed"}:
        raise ValueError("Both code and private seed archives are required")
    seen, contents = set(), {}
    for component, info in manifest["archives"].items():
        archive_path = regular(manifest_path.parent, info["name"])
        if archive_path.stat().st_size != info["bytes"] or sha256_file(archive_path) != info["sha256"]:
            raise ValueError("Archive SHA256/size verification failed")
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                path = safe_path(member.name)
                if path.parts[0] != release or len(path.parts) < 2:
                    raise ValueError("Archive root mismatch")
                name = "/".join(path.parts[1:])
                permitted_name(name)
                if name in seen or name not in expected or not member.isfile() or member.linkname:
                    raise ValueError("Unexpected, duplicate or non-regular archive member")
                item = expected[name]
                if item["component"] != component or member.mode != item["mode"] or member.size != item["bytes"]:
                    raise ValueError("Archive member metadata mismatch")
                stream = archive.extractfile(member)
                data = stream.read()
                if sha256_bytes(data) != item["sha256"]:
                    raise ValueError("Archive member SHA256 verification failed")
                seen.add(name)
                if extract_to is not None:
                    contents[name] = data
    if seen != set(expected):
        raise ValueError("Missing archive members")
    result = {"identity": IDENTITY, "release": release, "integrity": "ok", "file_count": len(seen),
              "component_counts": {c: sum(x["component"] == c for x in expected.values()) for c in manifest["archives"]}}
    if extract_to is not None:
        target = Path(extract_to).absolute()
        if target.exists() or target.is_symlink() or any(p.is_symlink() for p in target.parents):
            raise ValueError("Extraction destination must be a new non-symlink directory")
        target.mkdir(parents=True, mode=0o700)
        root = target / release
        root.mkdir(mode=0o700)
        for name, data in sorted(contents.items()):
            destination = root.joinpath(*safe_path(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with destination.open("xb") as stream:
                os.chmod(destination, expected[name]["mode"])
                stream.write(data)
        result["extracted_root"] = str(root.resolve())
    return result


def build(source, output_dir, tag=None):
    files = collect(source)
    tag = tag or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag):
        raise ValueError("Unsafe release tag")
    release = IDENTITY + "-" + tag
    output = Path(output_dir).absolute()
    if output.exists() or output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError("Output directory must be new and non-symlink")
    output.mkdir(parents=True, mode=0o700)
    archives = {}
    for component in ("code", "private_seed"):
        name = release + "-" + component + ".tar.gz"
        path = output / name
        write_archive(path, release, files, component)
        archives[component] = {"name": name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {"format": 1, "identity": IDENTITY, "release": release,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "private_seed_notice": "Private curriculum/teacher materials; distribute only to authorized operators.",
                "archives": archives,
                "files": {name: {"component": item["component"], "bytes": len(item["data"]),
                                  "sha256": sha256_bytes(item["data"]), "mode": item["mode"]}
                          for name, item in sorted(files.items())}}
    manifest_path = output / (release + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    checksums = output / (release + ".sha256")
    checksums.write_text("".join(info["sha256"] + "  " + info["name"] + "\n" for info in archives.values())
                         + sha256_file(manifest_path) + "  " + manifest_path.name + "\n", encoding="utf-8")
    os.chmod(checksums, 0o600)
    report = verify(manifest_path)
    report.update(manifest=str(manifest_path.resolve()), checksum_file=str(checksums.resolve()),
                  archives={c: str((output / info["name"]).resolve()) for c, info in archives.items()},
                  boundaries=["Local build only; no deployment or remote operations.",
                              "No live data/accounts/configuration included.",
                              "Private seed is separate from application code."])
    report_path = output / (release + ".report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.chmod(report_path, 0o600)
    report["report"] = str(report_path.resolve())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build")
    b.add_argument("--source-root", type=Path, default=APP_ROOT)
    b.add_argument("--output-dir", type=Path, required=True, help="New directory; existing directories are never overwritten")
    b.add_argument("--tag", help="Safe release suffix; defaults to a UTC timestamp")
    v = commands.add_parser("verify")
    v.add_argument("--manifest", type=Path, required=True)
    v.add_argument("--extract-to", type=Path, help="New private directory; extracts only after full verification")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        result = build(args.source_root, args.output_dir, args.tag) if args.command == "build" else verify(args.manifest, args.extract_to)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError):
        parser.exit(1, "Release build/verification failed; source is unchanged. Retain any incomplete new output privately.\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
