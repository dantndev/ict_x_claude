"""Centralized configuration: .env (pydantic-settings) + YAML overlay.

Layout:
    Settings   — from environment (.env): paths, URLs, symbol, log level.
    Config     — from YAML files (configs/default.yaml + configs/<symbol>.yaml):
                 sessions, killzones, detector thresholds, risk caps,
                 instrument specs. Loaded once and frozen.

Access pattern:
    from ict_bot.config.settings import get_settings, get_config
    s = get_settings()
    cfg = get_config(symbol_yaml="nq.yaml")
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[3]
CONFIGS_DIR: Path = REPO_ROOT / "configs"


class Settings(BaseSettings):
    """Environment-derived settings."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    ict_l2_csv_dir: Path = Field(
        default=Path("C:/claude_algo_4/analisis_ml_v1/Data_Historica_L2_V2"),
    )
    ict_backtest_api_url: str = Field(default="http://localhost:8080/backtest/")
    ict_symbol: str = Field(default="ENQM26")
    ict_continuous_symbol: str = Field(default="NQ")
    ict_timezone: str = Field(default="America/New_York")
    ict_log_level: str = Field(default="INFO")

    broker_name: str | None = Field(default=None)
    broker_api_key: str | None = Field(default=None)
    broker_api_secret: str | None = Field(default=None)
    broker_account_id: str | None = Field(default=None)
    broker_paper_mode: bool = Field(default=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursive dict merge — override wins; nested dicts merged."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, Mapping):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache(maxsize=8)
def get_config(symbol_yaml: str | None = "nq.yaml") -> dict[str, Any]:
    """Load configs/default.yaml + optional configs/<symbol>.yaml overlay."""
    default_path = CONFIGS_DIR / "default.yaml"
    with default_path.open("r", encoding="utf-8") as f:
        merged: dict[str, Any] = cast(dict[str, Any], yaml.safe_load(f) or {})

    if symbol_yaml:
        sym_path = CONFIGS_DIR / symbol_yaml
        if sym_path.exists():
            with sym_path.open("r", encoding="utf-8") as f:
                overlay = cast(dict[str, Any], yaml.safe_load(f) or {})
            merged = _deep_merge(merged, overlay)

    return merged
