"""Local-only administrator provisioning and scoped retention maintenance."""
import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import sqlite3
from .db import Database
from .models import validate_new_password
from .roster import maintenance


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local AIcademiya administration (no password command-line arguments)")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--email", required=True)
    cleanup = sub.add_parser("maintenance")
    cleanup.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    data = Path(os.getenv("AICADEMIYA_DATA_DIR", str(root / "data-v2")))
    db = Database(data / "aicademiya.sqlite3")
    if args.action == "create":
        if not args.name.strip() or "@" not in args.email or " " in args.email:
            parser.error("Provide a valid email and nonblank name")
        password = getpass("New admin password (8–512 characters, letter and digit): ")
        confirmation = getpass("Confirm password: ")
        try:
            validate_new_password(password)
        except ValueError:
            parser.error("Use 8–512 characters including a letter and digit")
        if password != confirmation:
            parser.error("Password confirmation differs")
    if args.action == "maintenance":
        if not db.path.is_file():
            parser.error("Existing migrated database is required for maintenance")
    else:
        db.initialize(root / "sample_data" / "catalog.json", demo_enabled=False)
    try:
        if args.action == "create":
            uid = db.create_admin(args.name, args.email, password)
            print(f"Admin created locally: {uid}")
        elif args.action == "promote":
            uid = db.promote_teacher(args.email)
            print(f"Teacher promoted locally: {uid}; existing sessions revoked")
        else:
            with db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                print(json.dumps(maintenance(conn, dry_run=args.dry_run)))
    except (ValueError, sqlite3.IntegrityError):
        parser.error("Account operation conflicts with existing data or requires an active teacher")
    return 0


if __name__ == "__main__":
    main()
