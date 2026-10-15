"""Effective server settings and last explicit checks, stored in existing settings/meta.

Credentials and configuration bindings are private. GET projections never perform
network requests; a connected check is historical evidence, not a health promise.
"""
import hashlib
import json
import os
import secrets

from fastapi import HTTPException

from .db import now

SEARCH_TEST_QUERY = "public education formative assessment research"
MODEL_CHECK_OK = "OpenAI-compatible endpoint returned a nonempty response."
MODEL_CHECK_ERROR = "Model connection check failed. Check endpoint, credentials, and service availability."
SEARCH_CHECK_OK = "Tavily returned a valid search response."
SEARCH_CHECK_ERROR = "Web search connection check failed. Check credentials, quota, and service availability."


def put_value(conn, table, key, value):
    # Only call with internal fixed table names, never request data.
    conn.execute(f"INSERT INTO {table}(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def check_snapshot(conn, service, config):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (f"service_{service}_revision",)).fetchone()
    return {"fingerprint": fingerprint(config), "revision": row[0] if row else ""}


def invalidate_check(conn, service):
    # A generation also detects concurrent A -> B -> A saves during a test.
    put_value(conn, "meta", f"service_{service}_revision", secrets.token_hex(16))
    conn.execute("DELETE FROM meta WHERE key=?", (f"service_{service}_connection",))


def connection_check(conn, service, config, *, configured, public=False):
    empty = {"status": "not_checked" if configured else "not_configured", "checked_at": None, "message": None}
    if not configured:
        return empty
    row = conn.execute("SELECT value FROM meta WHERE key=?", (f"service_{service}_connection",)).fetchone()
    if not row:
        return empty
    try:
        saved = json.loads(row[0])
        if saved["binding"] != check_snapshot(conn, service, config):
            return empty
        if saved["status"] not in ("connected", "error") or not isinstance(saved["checked_at"], str):
            return empty
        # Do not trust arbitrary/legacy diagnostic text from the database.
        message = ({"ai": MODEL_CHECK_OK, "search": SEARCH_CHECK_OK} if saved["status"] == "connected"
                   else {"ai": MODEL_CHECK_ERROR, "search": SEARCH_CHECK_ERROR})[service]
        return {"status": saved["status"], "checked_at": saved["checked_at"], "message": None if public else message}
    except (ValueError, KeyError, TypeError):
        return empty


def record_check(conn, service, snapshot, current_config, *, ok):
    """Call inside BEGIN IMMEDIATE after the network request, not during it."""
    if check_snapshot(conn, service, current_config) != snapshot:
        raise HTTPException(409, "Service settings changed during the connection check; test the saved settings again")
    put_value(conn, "meta", f"service_{service}_connection", json.dumps({
        "binding": snapshot, "status": "connected" if ok else "error", "checked_at": now(),
    }, separators=(",", ":")))


def effective_search_settings(conn=None):
    overrides = dict(conn.execute("SELECT key,value FROM settings WHERE key IN ('web_search_enabled','web_search_api_key')")) if conn is not None else {}
    enabled = overrides.get("web_search_enabled", os.getenv("AICADEMIYA_WEB_SEARCH_ENABLED", "false")).lower() == "true"
    if "web_search_api_key" in overrides:
        key = overrides["web_search_api_key"].strip()
        source = "saved" if key else "none"
    else:
        key = os.getenv("TAVILY_API_KEY", "").strip()
        source = "environment" if key else "none"
    return {"provider": "tavily", "enabled": enabled, "api_key": key, "api_key_source": source}


def search_projection(conn, *, public=False):
    settings = effective_search_settings(conn)
    configured = bool(settings["api_key"])
    return {"provider": "tavily", "enabled": settings["enabled"], "configured": configured,
            "api_key_set": configured, "api_key_source": settings["api_key_source"],
            "connection": connection_check(conn, "search", settings, configured=configured, public=public)}


def update_search_settings(conn, payload):
    before = effective_search_settings(conn)
    if payload.enabled is not None:
        put_value(conn, "settings", "web_search_enabled", "true" if payload.enabled else "false")
    if payload.clear_api_key:
        # Empty is an explicit override; an inherited key cannot silently revive.
        put_value(conn, "settings", "web_search_api_key", "")
    elif payload.api_key and payload.api_key.strip():
        put_value(conn, "settings", "web_search_api_key", payload.api_key.strip())
    if before != effective_search_settings(conn):
        invalidate_check(conn, "search")
    return search_projection(conn)
