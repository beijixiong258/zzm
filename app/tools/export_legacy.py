"""Export an existing SQLite workspace for the Java/MySQL application, read-only."""
import argparse
import base64
import json
import mimetypes
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def identity(*parts):
    return uuid.uuid5(uuid.NAMESPACE_URL, "aicademiya:" + ":".join(map(str, parts))).hex


def encoded(value):
    return json.dumps(value, ensure_ascii=False, default=lambda item: {"base64": base64.b64encode(item).decode("ascii")} if isinstance(item, bytes) else str(item))


def decode(value, fallback):
    if not value:
        return fallback
    return json.loads(value) if isinstance(value, str) else value


def text(value):
    if isinstance(value, list):
        return "\n".join(map(str, value))
    return str(value or "")


def content(detail):
    profile = detail.get("teaching_profile") or {}
    answers = detail.get("reference_answers") or {}
    types = {"open_response": "openResponse", "reading_response": "readingResponse", "fill_in_blank": "fillInBlank", "single_choice": "singleChoice", "image_matching": "imageMatching"}
    questions = []
    for original in detail.get("questions", []):
        options = [text(option) for option in original.get("options", [])]
        answer = text(answers.get(original["id"], original.get("reference_answer", "")))
        questions.append({"id": original["id"], "type": types.get(original.get("type"), "openResponse"), "prompt": original.get("prompt", ""),
                          "options": options, "referenceAnswer": answer, "explanation": original.get("explanation", ""), "hint": original.get("hint", ""),
                          "answerSlots": original.get("answer_slots", 1), "sourceMaterialIds": [], "imageMaterialIds": []})
    goals = detail.get("learning_objectives") or []
    if isinstance(goals, str):
        goals = goals.splitlines()
    plan = [{"title": phase.get("title") or phase.get("label") or phase.get("type", ""), "description": phase.get("instruction") or phase.get("description", ""), "durationMinutes": phase.get("duration_minutes", 0)} for phase in profile.get("phases", []) if isinstance(phase, dict)]
    return {"description": detail.get("subtitle", ""), "learningGoals": goals, "learningPlan": plan, "questions": questions,
            "openingMessage": profile.get("opening_message", ""), "aiConfig": {"teachingApproach": text(profile.get("background")),
            "feedbackStrategy": text(profile.get("response_strategies")), "responseDetail": profile.get("response_detail", ""), "tone": profile.get("tone", "")}}


def export(source, destination, catalog=None):
    if destination.exists():
        raise ValueError("Choose a new export directory; existing files are never overwritten")
    connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    tables = {name: [dict(row) for row in connection.execute('SELECT * FROM "' + name.replace('"', '""') + '"')] for name in names}
    connection.close()
    if not tables.get("users"):
        raise ValueError("The source has no accounts; use initial setup for a new database")
    now = datetime.now(timezone.utc).isoformat()
    app_root = Path(__file__).resolve().parents[1]
    def local_path(value):
        path = Path(value)
        return path.resolve() if path.is_absolute() else (app_root / path).resolve()
    if catalog is None:
        config_path = app_root / "config.json"
        settings = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.is_file() else {}
        catalog = local_path(settings.get("storage", {}).get("catalog_path", "local-demo/catalog.json"))
    asset_root = catalog.resolve().parent / "assets"
    users = [{"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"], "passwordHash": row.get("password_hash"),
              "archived": bool(row.get("archived_at")), "mustChangePassword": bool(row.get("must_change_password")), "demo": bool(row.get("is_demo"))} for row in tables["users"]]
    teachers = [row["id"] for row in users if row["role"] in ("teacher", "admin")]
    if tables.get("courses") and not teachers:
        raise ValueError("Assign a teacher to the existing courses before migration")
    courses = [{"id": row["id"], "code": row["code"], "title": row["title"], "description": row.get("description", ""), "ownerId": row.get("owner_id") or teachers[0],
                "systemInstructions": "", "joinCode": row["join_code"], "archived": bool(row.get("archived_at"))} for row in tables.get("courses", [])]
    members = {}
    for row in tables.get("course_staff", []) + [{"course_id": row["id"], "user_id": row["ownerId"]} for row in courses]:
        member_id = identity("member", row["course_id"], row["user_id"])
        members[member_id] = {"id": member_id, "courseId": row["course_id"], "userId": row["user_id"], "role": "teacher", "archived": False}
    for row in tables.get("enrollments", []):
        member_id = identity("member", row["course_id"], row["user_id"])
        if member_id not in members:
            members[member_id] = {"id": member_id, "courseId": row["course_id"], "userId": row["user_id"], "role": "student", "archived": bool(row.get("archived_at"))}
    session_course = {row["id"]: row["course_id"] for row in tables.get("sessions", [])}
    material_course = {row["material_id"]: row["course_id"] for row in tables.get("material_courses", [])}
    material_ids = {}
    for row in tables.get("session_materials", []):
        material_ids.setdefault(row["session_id"], []).append(row["material_id"])
    materials = []
    copy_files = []
    for row in tables.get("materials", []):
        info = decode(row["content_json"], {})
        course_id = material_course.get(row["id"], session_course.get(row.get("session_id")))
        if not course_id:
            continue
        path = local_path(row["file_path"]) if row.get("file_path") else None
        name = path.name if path else info.get("title", row["id"])
        relative = row["id"] + (path.suffix if path else ".txt")
        if path and path.is_file():
            copy_files.append((path, relative))
        materials.append({"id": row["id"], "courseId": course_id, "title": info.get("title", name), "fileName": name,
                          "relativePath": info.get("source_relative_path") or name, "mimeType": "application/pdf" if name.lower().endswith(".pdf") else "image/png" if name.lower().endswith(".png") else "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "application/octet-stream",
                          "storagePath": relative, "textContent": info.get("excerpt", ""), "status": "ready" if info.get("excerpt") else "failed",
                          "visibility": "student" if info.get("visibility", "student") == "student" else "teacher",
                          "errorMessage": info.get("warning") or "", "archived": bool(row.get("archived")), "createdAt": now})
    material_map = {row["id"]: row for row in materials}
    source_materials = {row["id"]: decode(row["content_json"], {}) for row in tables.get("materials", [])}

    def question_image(image, course_id):
        url = image.get("url", "").split("?", 1)[0]
        match = re.fullmatch(r"/api/materials/([^/]+)/assets/([^/]+)", url)
        if match:
            raw = source_materials.get(match[1], {})
            if not raw.get("assets_dir"):
                raise ValueError("A worksheet figure has no original asset directory")
            root = local_path(raw["assets_dir"])
            relative = match[2]
        elif url.startswith("/api/assets/"):
            root, relative = asset_root, url.removeprefix("/api/assets/")
        else:
            raise ValueError("A question figure uses an unsupported reference; review it before migration")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg"} or not path.is_file():
            raise ValueError("A question figure is missing or outside its asset directory")
        mid = identity("figure", course_id, url)
        if mid not in material_map:
            filename = mid + path.suffix.lower()
            figure = {"id": mid, "courseId": course_id, "title": image.get("label") or path.name,
                      "fileName": path.name, "relativePath": "figures/" + path.name,
                      "mimeType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                      "storagePath": filename, "textContent": image.get("alt") or image.get("label") or path.stem,
                      "status": "ready", "visibility": "student", "errorMessage": "", "archived": False, "createdAt": now}
            material_map[mid] = figure
            materials.append(figure)
            copy_files.append((path, filename))
        return mid

    def snapshot(detail, course_id, linked, version_id=None):
        linked = list(dict.fromkeys(linked))
        task_content = content(detail)
        for original, question in zip(detail.get("questions", []), task_content["questions"]):
            question["sourceMaterialIds"] = [mid for mid in original.get("source_material_ids", []) if mid in linked]
            question["imageMaterialIds"] = [question_image(image, course_id) for image in original.get("images", [])]
            linked.extend(mid for mid in question["imageMaterialIds"] if mid not in linked)
        snapshots = {item["id"]: decode(item.get("content_json"), item) for item in detail.get("_materials", [])}
        visible_materials = []
        for mid in linked:
            if mid not in material_map:
                continue
            item = {k: v for k, v in material_map[mid].items() if k not in ("storagePath", "textContent", "courseId")}
            saved = snapshots.get(mid)
            if saved:
                item["title"] = saved.get("title", item["title"])
                item["visibility"] = saved.get("visibility", item["visibility"])
            visible_materials.append(item)
        result = {"id": detail["id"], "courseId": course_id, "title": detail.get("title", ""), "description": detail.get("subtitle", ""),
                  "sessionType": "assignment" if detail.get("questions") else "tutor", "topic": "", "learningGoals": text(detail.get("learning_objectives")),
                  "additionalInstructions": detail.get("instructions", ""), "teachingLanguage": detail.get("teaching_language", "zh-CN"),
                  "materialIds": linked, "materials": visible_materials,
                  "content": task_content, "revision": 0, "publishedVersionId": version_id, "archived": False, "courseInstructions": ""}
        if version_id:
            result["versionId"] = version_id
        return result

    versions = []
    published = {row["id"]: row.get("published_version_id") for row in tables.get("courses", [])}
    current = {}
    version_by_pair = {}
    for row in tables.get("course_versions", []):
        old_snapshot = decode(row["snapshot_json"], {})
        for detail in old_snapshot.get("sessions", []):
            sid = detail["id"]
            if sid not in session_course:
                raise ValueError("A published task has no relational identity; repair the source before migration")
            vid = identity("version", row["id"], sid)
            linked = [m["id"] for m in detail.get("_materials", []) if m["id"] in material_map]
            value = snapshot(detail, row["course_id"], linked, vid)
            value["revision"] = row["number"]
            versions.append({"id": vid, "sessionId": sid, "courseId": row["course_id"], "revision": row["number"], "label": row["label"], "contentJson": encoded(value), "createdAt": row["created_at"]})
            version_by_pair[(row["id"], sid)] = vid
            if published.get(row["course_id"]) == row["id"]:
                current[sid] = vid
    sessions = []
    for row in tables.get("sessions", []):
        detail = decode(row["content_json"], {})
        value = snapshot(detail, row["course_id"], material_ids.get(row["id"], []), current.get(row["id"]))
        value["revision"] = max([v["revision"] for v in versions if v["sessionId"] == row["id"]] + [0]) + 1
        value["archived"] = not bool(row.get("in_draft", 1))
        value["materialIdsJson"] = encoded(value.pop("materialIds")); value["contentJson"] = encoded(value.pop("content"))
        value.pop("materials"); value.pop("courseInstructions"); value.pop("versionId", None)
        sessions.append(value)
    students = {row["id"] for row in users if row["role"] == "student"}
    records = []
    statuses = {"not_started": "notStarted", "in_progress": "inProgress", "needs_revision": "needsRevision"}
    attempts = {}
    for row in tables.get("attempts", []):
        attempts.setdefault((row["session_id"], row["user_id"], row.get("version_id", "")), {})[row["question_id"]] = row["answer"]
    messages = {}
    for row in sorted(tables.get("messages", []), key=lambda item: item.get("seq", 0)):
        messages.setdefault((row["session_id"], row["user_id"], row.get("version_id", "")), []).append({"role": row["role"], "content": row["content"], "createdAt": row["created_at"], "legacyMessageId": row["id"], "citations": decode(row.get("citations_json"), [])})
    for row in tables.get("workspaces", []):
        if row["user_id"] not in students:
            continue
        key = (row["session_id"], row["user_id"], row.get("version_id", ""))
        vid = version_by_pair.get((key[2], key[0]))
        if vid is None:
            # Do not silently bind historic work to the current published task.
            raise ValueError("A student workspace has no matching published version; source data needs review")
        records.append({"id": identity("record", *key), "sessionId": key[0], "userId": key[1], "versionId": vid, "status": statuses.get(row["status"], row["status"]),
                        "answersJson": encoded(attempts.get(key, {})), "messagesJson": encoded(messages.get(key, [])), "legacyJson": encoded(row), "revision": 0,
                        "startedAt": row.get("last_active"), "updatedAt": row.get("last_active"), "submittedAt": row.get("submitted_at"), "reviewedAt": row.get("reviewed_at"), "teacherNote": row.get("teacher_note", "")})
    legacy = []
    for name, rows in tables.items():
        for index, row in enumerate(rows):
            legacy.append({"id": identity("legacy", name, index), "sourceTable": name, "sourceKey": str(index), "payloadJson": encoded(row)})
    manifest = {"users": users, "courses": courses, "members": list(members.values()), "materials": materials, "sessions": sessions, "versions": versions, "records": records, "legacy": legacy}
    for rows in manifest.values():
        for row in rows:
            for field in ("createdAt", "startedAt", "updatedAt", "submittedAt", "reviewedAt"):
                if row.get(field):
                    value = datetime.fromisoformat(row[field].replace("Z", "+00:00"))
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=timezone.utc)
                    row[field] = value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="milliseconds")
    destination.mkdir(parents=True)
    (destination / "files").mkdir()
    for source_file, filename in copy_files:
        shutil.copyfile(source_file, destination / "files" / filename)
    (destination / "manifest.json").write_text(encoded(manifest), encoding="utf-8")
    print(encoded({"exportDirectory": str(destination.resolve()), "counts": {name: len(rows) for name, rows in manifest.items()}, "originalFilesCopied": len(copy_files)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--catalog", type=Path)
    arguments = parser.parse_args()
    export(arguments.database, arguments.output, arguments.catalog)
