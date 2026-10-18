"""Loads settings from .env. Keys are never hardcoded or printed."""
import os
from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    pass


def get_setting(name, default=None):
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise ConfigError(f"Missing required setting: {name} (add it to .env)")
    return value.strip()


def get_timeout(name, default):
    """Seconds to wait for an IBM call, from the environment variable name or default. Sprint 3:
    overridable so a real timeout can be produced on demand, e.g. STT_TIMEOUT=0.001."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return float(default)
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number of seconds, not {raw.strip()!r}")
    if value <= 0:
        raise ConfigError(f"{name} must be more than 0 seconds")
    return value


def watsonx_settings():
    return {
        "api_key": get_setting("WATSONX_API_KEY"),
        "project_id": get_setting("WATSONX_PROJECT_ID"),
        "url": get_setting("WATSONX_URL").rstrip("/"),
        "model_id": get_setting("WATSONX_MODEL_ID", "ibm/granite-4-h-small"),
    }
