"""Single local deployment file. Secrets are never included in diagnostics."""
from copy import deepcopy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 18773, "open_browser": True},
    "frontend": {"host": "127.0.0.1", "port": 18774},
    "storage": {"data_dir": "./data-local", "catalog_path": "./local-demo/catalog.json", "upload_dir": "./data-local/uploads", "frontend_dir": "./frontend/dist"},
    "auth": {"demo_enabled": True, "registration_enabled": False, "cookie_secure": False, "allowed_origins": [], "allowed_hosts": []},
    "ai": {
        "provider": "siliconflow", "mode": "openai",
        "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen3.8-27B",
        "api_key": "", "use_environment_proxy": False,
        "timeout_seconds": 120, "temperature": 0.3,
        "enable_thinking": False, "thinking_budget": 4096,
    },
    "search": {"enabled": False, "api_key": ""},
    "documents": {"worker_command": [], "formats": ["pdf"], "worker_timeout_seconds": 3600},
}
ENV_FIELDS = {
    "storage.data_dir": "AICADEMIYA_DATA_DIR", "storage.catalog_path": "AICADEMIYA_CATALOG_PATH",
    "storage.upload_dir": "AICADEMIYA_UPLOAD_DIR", "storage.frontend_dir": "AICADEMIYA_FRONTEND_DIR",
    "auth.demo_enabled": "AICADEMIYA_DEMO_ENABLED", "auth.registration_enabled": "AICADEMIYA_REGISTRATION_ENABLED",
    "auth.cookie_secure": "AICADEMIYA_COOKIE_SECURE", "auth.allowed_origins": "AICADEMIYA_ALLOWED_ORIGINS", "auth.allowed_hosts": "AICADEMIYA_ALLOWED_HOSTS",
    "ai.provider": "AICADEMIYA_AI_PROVIDER", "ai.mode": "AICADEMIYA_AI_MODE", "ai.base_url": "AICADEMIYA_AI_BASE_URL", "ai.model": "AICADEMIYA_AI_MODEL", "ai.api_key": "AICADEMIYA_AI_API_KEY", "ai.use_environment_proxy": "AICADEMIYA_USE_ENVIRONMENT_PROXY",
    "ai.timeout_seconds": "AICADEMIYA_AI_TIMEOUT_SECONDS", "ai.temperature": "AICADEMIYA_AI_TEMPERATURE",
    "ai.enable_thinking": "AICADEMIYA_AI_ENABLE_THINKING", "ai.thinking_budget": "AICADEMIYA_AI_THINKING_BUDGET",
    "search.enabled": "AICADEMIYA_WEB_SEARCH_ENABLED", "search.api_key": "TAVILY_API_KEY",
    "documents.worker_command": "AICADEMIYA_DOCUMENT_WORKER_COMMAND", "documents.formats": "AICADEMIYA_DOCUMENT_FORMATS", "documents.worker_timeout_seconds": "AICADEMIYA_DOCUMENT_WORKER_TIMEOUT",
}

def load_config(path=None):
    path = Path(path or ROOT / "config.json").resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError("Cannot read config.json. Provide a valid UTF-8 JSON configuration file.") from None
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError("Unknown configuration section in config.json.")
    config = deepcopy(DEFAULTS)
    for section, values in data.items():
        if not isinstance(values, dict) or set(values) - set(DEFAULTS[section]):
            raise ValueError(f"Unknown configuration option in {section}.")
        for key, value in values.items():
            default = DEFAULTS[section][key]
            valid_type = type(value) in (int, float) if isinstance(default, float) else type(value) is type(default)
            if not valid_type or isinstance(value, list) and not all(isinstance(item, str) for item in value):
                raise ValueError(f"Invalid type for {section}.{key}.")
            config[section][key] = value
    for section in ("server", "frontend"):
        if not 1 <= config[section]["port"] <= 65535 or not config[section]["host"].strip():
            raise ValueError(f"Invalid host or port in {section}.")
    if config["auth"]["demo_enabled"] and config["server"]["host"] not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Demo sign-in requires a loopback server host.")
    if config["ai"]["mode"] not in {"openai", "demo"}:
        raise ValueError("ai.mode must be openai or demo.")
    if not 1 <= config["ai"]["timeout_seconds"] <= 600:
        raise ValueError("ai.timeout_seconds must be between 1 and 600.")
    if not 0 <= config["ai"]["temperature"] <= 2:
        raise ValueError("ai.temperature must be between 0 and 2.")
    if not 128 <= config["ai"]["thinking_budget"] <= 32768:
        raise ValueError("ai.thinking_budget must be between 128 and 32768.")
    if not 1 <= config["documents"]["worker_timeout_seconds"] <= 86400:
        raise ValueError("documents.worker_timeout_seconds must be between 1 and 86400.")
    for key, value in config["storage"].items():
        if not value.strip():
            raise ValueError(f"storage.{key} must be a nonempty path.")
        resolved = Path(value)
        config["storage"][key] = str((path.parent / resolved).resolve() if not resolved.is_absolute() else resolved.resolve())
    return config

def config_environment(config, base=None):
    env = dict(os.environ if base is None else base)
    for field, variable in ENV_FIELDS.items():
        section, key = field.split(".")
        value = config[section][key]
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, list):
            value = json.dumps(value) if key == "worker_command" else ",".join(value)
        env[variable] = str(value)
    # The file is authoritative for deployment settings. Legacy DB rows remain intact.
    env["AICADEMIYA_CONFIG_MANAGED"] = "true"
    if not config["ai"]["use_environment_proxy"]:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)
    return env

def file_managed():
    return os.getenv("AICADEMIYA_CONFIG_MANAGED") == "true"
