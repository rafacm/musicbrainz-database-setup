from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MIRROR = "https://data.metabrainz.org/pub/musicbrainz/data/fullexport/"
DEFAULT_SQL_REF = "master"
ALL_MODULES = (
    "core",
    "derived",
    "editor",
    "edit",
    "cover-art",
    "event-art",
    "stats",
    "documentation",
    "wikidocs",
    "cdstubs",
)


def _xdg_cache_home() -> Path:
    env = os.environ.get("XDG_CACHE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".cache"


def default_workdir() -> Path:
    return _xdg_cache_home() / "musicbrainz-db-setup" / "dumps"


def default_sql_cache_dir() -> Path:
    return _xdg_cache_home() / "musicbrainz-db-setup" / "sql"


class Settings(BaseSettings):
    """Runtime configuration.

    Precedence: CLI flags (applied by caller) > env vars > .env > defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="MUSICBRAINZ_DB_SETUP_",
        env_file=".env",
        extra="ignore",
    )

    db_url: str | None = Field(default=None, description="libpq connection string")
    mirror_url: str = DEFAULT_MIRROR
    sql_ref: str = DEFAULT_SQL_REF
    workdir: Path = Field(default_factory=default_workdir)
    sql_cache_dir: Path = Field(default_factory=default_sql_cache_dir)
    modules: tuple[str, ...] = ("core",)
    verify_gpg: bool = False
    allow_schema_mismatch: bool = False
    log_file: Path | None = None
    verbose: bool = False
    quiet: bool = False
    yes: bool = False


def load() -> Settings:
    return Settings()
