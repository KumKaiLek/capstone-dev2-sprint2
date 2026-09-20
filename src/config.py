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


def watsonx_settings():
    return {
        "api_key": get_setting("WATSONX_API_KEY"),
        "project_id": get_setting("WATSONX_PROJECT_ID"),
        "url": get_setting("WATSONX_URL").rstrip("/"),
        "model_id": get_setting("WATSONX_MODEL_ID", "ibm/granite-4-h-small"),
    }
