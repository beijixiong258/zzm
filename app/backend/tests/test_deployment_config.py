"""Configuration is local, authoritative, validated and never exposes secrets."""
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.deployment_config import DEFAULTS, config_environment, load_config


def write_config(tmp_path, change=None):
    value = deepcopy(DEFAULTS)
    if change:
        change(value)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_paths_are_relative_to_configuration_not_working_directory(tmp_path, monkeypatch):
    path = write_config(tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(path)
    assert config["storage"]["data_dir"] == str(tmp_path / "data-local")
    assert config["storage"]["catalog_path"] == str(tmp_path / "local-demo" / "catalog.json")


def test_file_overrides_legacy_environment_and_disables_proxy(tmp_path):
    config = load_config(write_config(tmp_path))
    env = config_environment(config, {"AICADEMIYA_AI_API_KEY": "stale-key", "HTTPS_PROXY": "http://proxy", "OTHER": "keep"})
    assert env["AICADEMIYA_AI_API_KEY"] == ""
    assert env["AICADEMIYA_CONFIG_MANAGED"] == "true"
    assert env["AICADEMIYA_AI_PROVIDER"] == "siliconflow"
    assert env["AICADEMIYA_AI_BASE_URL"] == "https://api.siliconflow.cn/v1"
    assert env["AICADEMIYA_AI_MODEL"] == "Qwen/Qwen3.8-27B"
    assert "HTTPS_PROXY" not in env
    assert env["OTHER"] == "keep"


@pytest.mark.parametrize("change", [
    lambda c: c["server"].update(port=True),
    lambda c: c["server"].update(port=70000),
    lambda c: c["server"].update(host="0.0.0.0"),
    lambda c: c["ai"].update(api_key={"private": "DO_NOT_PRINT"}),
    lambda c: c["ai"].update(timeout_seconds=0),
    lambda c: c["ai"].update(timeout_seconds=601),
    lambda c: c["ai"].update(temperature=True),
    lambda c: c["ai"].update(temperature=-0.1),
    lambda c: c["ai"].update(temperature=2.1),
    lambda c: c["ai"].update(temperature=float("nan")),
    lambda c: c["ai"].update(enable_thinking="false"),
    lambda c: c["ai"].update(thinking_budget=127),
    lambda c: c["ai"].update(thinking_budget=32769),
    lambda c: c["documents"].update(worker_command="shell command"),
    lambda c: c["storage"].update(data_dir=""),
])
def test_invalid_configuration_fails_without_secret_values(tmp_path, change):
    with pytest.raises(ValueError) as error:
        load_config(write_config(tmp_path, change))
    assert "DO_NOT_PRINT" not in str(error.value)


def test_model_options_accept_integer_temperature_and_reach_environment(tmp_path):
    config = load_config(write_config(tmp_path, lambda c: c["ai"].update(
        temperature=0, timeout_seconds=150, enable_thinking=True, thinking_budget=2048)))
    env = config_environment(config, {})
    assert env["AICADEMIYA_AI_TEMPERATURE"] == "0"
    assert env["AICADEMIYA_AI_TIMEOUT_SECONDS"] == "150"
    assert env["AICADEMIYA_AI_ENABLE_THINKING"] == "true"
    assert env["AICADEMIYA_AI_THINKING_BUDGET"] == "2048"


def test_managed_model_and_search_ignore_old_database_settings(tmp_path, monkeypatch, app):
    config = load_config(write_config(tmp_path))
    for key, value in config_environment(config, {}).items():
        monkeypatch.setenv(key, value)
    from backend.aicademiya.service_settings import effective_search_settings
    from backend.aicademiya.access_control import registration_enabled
    with TestClient(app), app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('ai_api_key','legacy-key')")
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('web_search_enabled','true')")
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('web_search_api_key','legacy-key')")
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('registration_enabled','true')")
        assert app.state.tutor.settings(conn)["api_key"] == ""
        assert effective_search_settings(conn)["enabled"] is False
        assert effective_search_settings(conn)["api_key"] == ""
        assert registration_enabled(conn) is False
        assert conn.execute("SELECT value FROM settings WHERE key='ai_api_key'").fetchone()[0] == "legacy-key"
