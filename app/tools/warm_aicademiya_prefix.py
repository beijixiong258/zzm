#!/usr/bin/env python3
"""Local admin only: list topics, or warm exactly one student-free tutor prefix.

Run from app root with the deployment venv; --db points to an authorized EXISTING
SQLite database. Reads courses/materials only, never users/workspaces/messages.
No app initialization, credentials, dataset edits, or automatic all-GPU warm.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

import httpx
from fastapi import HTTPException
from backend.aicademiya.ai import published_prefix

WARM_URL = "http://127.0.0.1:18280/admin/cache/warm"


@contextmanager
def read_database(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Existing authorized database required; this tool never initializes one.")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        # Consistent static configuration even if a teacher edits during the read.
        conn.execute("BEGIN")
        yield conn
    finally:
        conn.close()


def topics(conn):
    for row in conn.execute("SELECT v.snapshot_json FROM courses c JOIN course_versions v ON v.id=c.published_version_id ORDER BY c.id"):
        content = json.loads(row["snapshot_json"])
        for detail in sorted(content.get("sessions", []), key=lambda item: item["id"]):
            if detail.get("status") != "published":
                continue
            for question in detail.get("questions", []):
                yield {"session": detail["id"], "question": question["id"]}


def prefix_message(conn, session_id, question_id):
    # Published snapshot and source filtering must match the real student tutor,
    # not a teacher's unpublished edits. This helper reads no student tables.
    return published_prefix(conn, session_id, question_id)


def warm(message, workers, *, transport=None):
    # Router builds the exact chat-template prefix up to the first user header;
    # do NOT send a virtual user here, nor student history or dynamic state.
    payload = {"messages": [message], "workers": workers}
    with httpx.Client(timeout=httpx.Timeout(600, connect=10), trust_env=False,
                      follow_redirects=False, transport=transport) as client:
        response = client.post(WARM_URL, json=payload)
    if not response.is_success:
        # Provider errors may echo a private reference; never print the body.
        raise ValueError(f"Router warm returned HTTP {response.status_code}; inspect server-side admin logs privately.")
    # Do not echo response JSON: admin implementations may include prompt text.
    return response.status_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("AICADEMIYA_DATA_DIR", str(APP / "data"))) / "aicademiya.sqlite3",
                        help="Existing authorized local database (read-only).")
    parser.add_argument("--session", help="Exact session ID; requires --question, executes one warm.")
    parser.add_argument("--question", help="Exact question ID; requires --session.")
    parser.add_argument("--workers", nargs="+", choices=("v100", "t10a", "t10b"), default=["v100"],
                        help="Explicit worker selection; default warms v100 only, not all GPUs.")
    args = parser.parse_args(argv)
    if bool(args.session) != bool(args.question):
        parser.error("--session and --question must be supplied together")
    try:
        with read_database(args.db) as conn:
            if args.session is None:
                print(json.dumps({"topics": list(topics(conn)), "action": "list_only"}, ensure_ascii=False))
                return 0
            message = prefix_message(conn, args.session, args.question)
        status = warm(message, list(dict.fromkeys(args.workers)))
        content = message["content"].encode("utf-8")
        print(json.dumps({"action": "warm_http_success", "session": args.session, "question": args.question,
                          "workers": list(dict.fromkeys(args.workers)), "http_status": status,
                          "prefix_sha256": hashlib.sha256(content).hexdigest(), "prefix_bytes": len(content)}))
        return 0
    except (ValueError, sqlite3.Error, httpx.HTTPError, HTTPException, KeyError, TypeError):
        # No exception repr, SQL text, server body, or course/reference contents.
        print("Warm/list failed. Check database/schema, IDs, and local router admin logs privately. No private prompt was printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
