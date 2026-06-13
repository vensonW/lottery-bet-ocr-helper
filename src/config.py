from __future__ import annotations

import configparser
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


INI_CONFIG_FILE = "config.ini"
LEGACY_JSON_CONFIG_FILE = "config.json"


@dataclass
class AppConfig:
    api_key: str = ""
    model: str = "gpt-5.5"
    base_url: str = ""
    proxy: str = ""
    default_job_count: int = 3
    default_output_dir: str = "outputs"
    max_image_side: int = 2048
    retry_count: int = 2
    ai_timeout_seconds: int = 120

    def resolved_api_key(self) -> str:
        return self.api_key.strip() or os.environ.get("OPENAI_API_KEY", "").strip()


def load_config(root_dir: Path) -> AppConfig:
    """优先读取 config.ini；如果不存在，则兼容读取旧的 config.json。"""
    config = _load_legacy_json(root_dir / LEGACY_JSON_CONFIG_FILE)
    ini_path = root_dir / INI_CONFIG_FILE
    if ini_path.exists():
        config = _load_ini_config(ini_path, config)
    return config


def _load_legacy_json(path: Path) -> AppConfig:
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        base = asdict(AppConfig())
        base.update({k: v for k, v in data.items() if k in base})
        return AppConfig(**base)
    except Exception:
        return AppConfig()


def _load_ini_config(path: Path, config: AppConfig) -> AppConfig:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8-sig")
    except Exception:
        return config

    if parser.has_section("openai"):
        config.api_key = parser.get("openai", "api_key", fallback=config.api_key).strip()
        config.model = parser.get("openai", "model", fallback=config.model).strip() or config.model
        config.base_url = parser.get("openai", "base_url", fallback=config.base_url).strip()
        config.proxy = parser.get("openai", "proxy", fallback=config.proxy).strip()

    if parser.has_section("app"):
        config.default_job_count = parser.getint("app", "job", fallback=config.default_job_count)
        config.default_output_dir = parser.get("app", "output_dir", fallback=config.default_output_dir).strip() or config.default_output_dir
        config.max_image_side = parser.getint("app", "max_image_side", fallback=config.max_image_side)
        config.retry_count = parser.getint("app", "retries", fallback=config.retry_count)
        config.ai_timeout_seconds = parser.getint("app", "ai_timeout_seconds", fallback=config.ai_timeout_seconds)

    # 兼容把 api_key/model 写在 DEFAULT 的简写方式。
    defaults = parser.defaults()
    if defaults:
        config.api_key = defaults.get("api_key", config.api_key).strip()
        config.model = defaults.get("model", config.model).strip() or config.model
        config.base_url = defaults.get("base_url", config.base_url).strip()
        config.proxy = defaults.get("proxy", config.proxy).strip()

    return config


def save_config(root_dir: Path, config: AppConfig) -> None:
    """保存到 config.ini。"""
    path = root_dir / INI_CONFIG_FILE
    parser = configparser.ConfigParser()
    parser["openai"] = {
        "api_key": config.api_key,
        "model": config.model,
        "base_url": config.base_url,
        "proxy": config.proxy,
    }
    parser["app"] = {
        "job": str(config.default_job_count),
        "output_dir": config.default_output_dir,
        "max_image_side": str(config.max_image_side),
        "retries": str(config.retry_count),
        "ai_timeout_seconds": str(config.ai_timeout_seconds),
    }
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)


def resolve_app_path(root_dir: Path, value: str | Path | None, default: str | Path) -> Path:
    raw = Path(value or default)
    if raw.is_absolute():
        return raw
    return root_dir / raw
