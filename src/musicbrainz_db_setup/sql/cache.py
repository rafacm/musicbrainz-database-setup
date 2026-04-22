from __future__ import annotations

from pathlib import Path

from musicbrainz_db_setup.config import default_sql_cache_dir


def sql_cache_path(commit_sha: str, repo_path: str, *, root: Path | None = None) -> Path:
    root = root or default_sql_cache_dir()
    # Strip any leading components of repo_path so we end up with a deterministic layout
    # rooted at <root>/<sha>/admin/sql/...
    return root / commit_sha / repo_path
