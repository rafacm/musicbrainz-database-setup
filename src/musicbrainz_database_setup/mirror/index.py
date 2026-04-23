"""Parse the MusicBrainz mirror's fullexport index to find dated dump directories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from musicbrainz_database_setup.errors import NetworkError
from musicbrainz_database_setup.mirror.client import http_client

DATED_DIR_RE = re.compile(r'href="(\d{8}-\d{6})/"', re.IGNORECASE)
LATEST_FILENAME = "LATEST"


@dataclass(frozen=True, slots=True)
class DumpDirectory:
    name: str  # e.g. "20260408-002212"
    url: str  # full URL with trailing slash


def list_dated_dirs(mirror_url: str, *, limit: int | None = None) -> list[DumpDirectory]:
    base = mirror_url if mirror_url.endswith("/") else mirror_url + "/"
    with http_client() as client:
        try:
            resp = client.get(base)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NetworkError(f"Failed to list {base}: {exc}") from exc
    names = sorted(set(DATED_DIR_RE.findall(resp.text)), reverse=True)
    if limit is not None:
        names = names[:limit]
    return [DumpDirectory(name=n, url=urljoin(base, f"{n}/")) for n in names]


def resolve_latest(mirror_url: str) -> DumpDirectory:
    base = mirror_url if mirror_url.endswith("/") else mirror_url + "/"
    url = urljoin(base, LATEST_FILENAME)
    with http_client() as client:
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NetworkError(f"Failed to fetch {url}: {exc}") from exc
    name = resp.text.strip().rstrip("/")
    if not re.fullmatch(r"\d{8}-\d{6}", name):
        raise NetworkError(f"Unexpected LATEST contents: {name!r}")
    return DumpDirectory(name=name, url=urljoin(base, f"{name}/"))


def build_dated_dir(mirror_url: str, name: str) -> DumpDirectory:
    base = mirror_url if mirror_url.endswith("/") else mirror_url + "/"
    if not re.fullmatch(r"\d{8}-\d{6}", name):
        raise ValueError(f"Invalid dated dir name: {name!r}")
    return DumpDirectory(name=name, url=urljoin(base, f"{name}/"))
