"""Resumable streaming downloads with rich progress."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urljoin

import httpx

from musicbrainz_db_setup.errors import ChecksumError, NetworkError
from musicbrainz_db_setup.mirror.checksums import Checksums, parse, verify_file
from musicbrainz_db_setup.mirror.client import http_client
from musicbrainz_db_setup.mirror.index import DumpDirectory
from musicbrainz_db_setup.progress import ProgressManager

log = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 MiB


def fetch_checksums(dump_dir: DumpDirectory) -> Checksums:
    with http_client() as client:
        for fname, algo in (("SHA256SUMS", "sha256"), ("MD5SUMS", "md5")):
            url = urljoin(dump_dir.url, fname)
            resp = client.get(url)
            if resp.status_code == 200:
                return parse(resp.text, algo)
    raise NetworkError(f"No SHA256SUMS or MD5SUMS found at {dump_dir.url}")


def download_archive(
    dump_dir: DumpDirectory,
    archive_name: str,
    dest_dir: Path,
    *,
    checksums: Checksums,
    verify: bool = True,
) -> Path:
    """Download one archive with resume + checksum verification.

    Returns the path to the verified archive. ``.part`` file is kept between
    attempts so crashes resume from the last flushed byte.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / archive_name
    part = dest_dir / f"{archive_name}.part"
    url = urljoin(dump_dir.url, archive_name)

    expected = checksums.digest_for(archive_name)
    if verify and expected is None:
        raise ChecksumError(
            f"{archive_name} missing from {checksums.algo.upper()}SUMS"
        )

    if final.exists() and verify and expected is not None:
        verify_file(final, expected, checksums.algo)
        log.info("Archive %s already present and verified.", archive_name)
        return final

    offset = part.stat().st_size if part.exists() else 0
    headers: dict[str, str] = {}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"

    pm = ProgressManager.instance()
    task_id = pm.add_task(f"Download {archive_name}", total=None, note="")

    try:
        with http_client() as client, client.stream("GET", url, headers=headers) as resp:
            if resp.status_code in (200, 206):
                pass
            else:
                raise NetworkError(
                    f"GET {url} returned HTTP {resp.status_code}"
                )
            total_from_header = _total_size(resp, offset)
            pm.update(task_id, total=total_from_header, completed=offset)

            mode = "ab" if resp.status_code == 206 else "wb"
            if mode == "wb":
                offset = 0
            with part.open(mode) as f:
                for chunk in resp.iter_bytes(_CHUNK):
                    if not chunk:
                        continue
                    f.write(chunk)
                    pm.advance(task_id, len(chunk))
    except httpx.HTTPError as exc:
        raise NetworkError(f"Download of {url} failed: {exc}") from exc

    if verify and expected is not None:
        verify_file(part, expected, checksums.algo)
    part.replace(final)
    return final


def _total_size(resp: httpx.Response, offset: int) -> int | None:
    # 206 -> Content-Range: bytes 100-999/1000
    cr = resp.headers.get("Content-Range")
    if cr and "/" in cr:
        try:
            return int(cr.rsplit("/", 1)[1])
        except ValueError:
            pass
    cl = resp.headers.get("Content-Length")
    if cl is not None:
        try:
            return int(cl) + offset
        except ValueError:
            pass
    return None
