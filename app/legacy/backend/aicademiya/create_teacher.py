"""Provision a real teacher interactively; passwords never appear in argv/logs."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import sqlite3
from .db import Database
from .models import validate_new_password
from .deployment_config import load_config


def main():
    parser = argparse.ArgumentParser(description="Create an AIcademiya teacher without enabling demo authentication")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--config", type=Path)
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
    config_path = args.config or root / "config.json"
    storage = load_config(config_path)["storage"] if args.config or config_path.is_file() else {}
    data = Path(storage.get("data_dir", os.getenv("AICADEMIYA_DATA_DIR", str(root / "data-v2"))))
    database = Database(data / "aicademiya.sqlite3")
    database.initialize(Path(storage.get("catalog_path", str(root / "sample_data" / "catalog.json"))), demo_enabled=False)
    try:
        uid = database.create_teacher(args.name, args.email, password)
    except sqlite3.IntegrityError:
        parser.error("That email already exists")
    print(f"Teacher created: {uid}. Sign in through /api/auth/login.")


if __name__ == "__main__":
    main()
