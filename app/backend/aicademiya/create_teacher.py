"""Provision a real teacher interactively; passwords never appear in argv/logs."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import sqlite3
from .db import Database
from .models import validate_new_password


def main():
    parser = argparse.ArgumentParser(description="Create an AIcademiya teacher without enabling demo authentication")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if "@" not in args.email or not args.name.strip():
        parser.error("Provide a valid email and nonblank name")
    password = getpass("New teacher password (8+ characters, letter and digit): ")
    confirmation = getpass("Confirm password: ")
    try:
        validate_new_password(password)
    except ValueError:
        parser.error("Use 8–512 characters including a letter and a digit")
    if password != confirmation:
        parser.error("Password confirmation differs")
    root = Path(__file__).resolve().parents[2]
    data = Path(os.getenv("AICADEMIYA_DATA_DIR", str(root / "data-v2")))
    database = Database(data / "aicademiya.sqlite3")
    database.initialize(root / "sample_data" / "catalog.json", demo_enabled=False)
    try:
        uid = database.create_teacher(args.name, args.email, password)
    except sqlite3.IntegrityError:
        parser.error("That email already exists")
    print(f"Teacher created: {uid}. Sign in through /api/auth/login.")


if __name__ == "__main__":
    main()
