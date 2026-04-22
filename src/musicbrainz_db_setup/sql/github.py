"""Fetch admin/sql/*.sql from metabrainz/musicbrainz-server at a configurable ref.

A ref (branch, tag, or SHA) is resolved once to a commit SHA via the GitHub
API; the SHA keys the on-disk cache so moving refs like ``master`` invalidate
naturally on a new commit.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from musicbrainz_db_setup.errors import NetworkError
from musicbrainz_db_setup.mirror.client import http_client
from musicbrainz_db_setup.sql.cache import sql_cache_path

log = logging.getLogger(__name__)

REPO = "metabrainz/musicbrainz-server"
RAW_TEMPLATE = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"
COMMIT_TEMPLATE = "https://api.github.com/repos/{repo}/commits/{ref}"


def resolve_ref(ref: str) -> str:
    """Resolve ``ref`` to a commit SHA. Accepts a SHA directly."""
    if _looks_like_sha(ref):
        return ref
    url = COMMIT_TEMPLATE.format(repo=REPO, ref=ref)
    with http_client() as client:
        try:
            resp = client.get(url, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NetworkError(f"Failed to resolve ref {ref!r}: {exc}") from exc
    sha = resp.json().get("sha")
    if not isinstance(sha, str) or not _looks_like_sha(sha):
        raise NetworkError(f"GitHub did not return a SHA for {ref!r}: {resp.text[:200]!r}")
    log.debug("Resolved ref %r to %s", ref, sha)
    return sha


def fetch(repo_path: str, *, sha: str, cache_root: Path | None = None) -> Path:
    """Return a local path to the cached SQL file, downloading if needed."""
    dest = sql_cache_path(sha, repo_path, root=cache_root)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = RAW_TEMPLATE.format(repo=REPO, sha=sha, path=repo_path)
    with http_client() as client:
        try:
            resp = client.get(url)
            if resp.status_code == 404:
                raise NetworkError(f"Not found: {url}")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NetworkError(f"GET {url} failed: {exc}") from exc
    dest.write_text(resp.text, encoding="utf-8")
    return dest


def _looks_like_sha(value: str) -> bool:
    return len(value) in {7, 8, 9, 10, 40} and all(c in "0123456789abcdef" for c in value.lower())
