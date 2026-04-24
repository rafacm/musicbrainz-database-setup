"""Iterate TSV members of a MusicBrainz dump archive without extracting to disk."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DumpMember:
    table_name: str  # last path component of mbdump/<table>
    size: int
    file: IO[bytes]


def _parallel_bz2_tool() -> str | None:
    """Return the absolute path of ``pbzip2`` or ``lbzip2`` if available, else ``None``."""
    return shutil.which("pbzip2") or shutil.which("lbzip2")


@contextmanager
def open_archive(path: Path) -> Iterator[tarfile.TarFile]:
    """Open a ``tar.bz2`` in streaming mode.

    If ``pbzip2`` or ``lbzip2`` is on ``$PATH``, pipes the archive through it
    for parallel decompression and reads the uncompressed tar stream from the
    subprocess's stdout. Otherwise falls back to CPython's single-threaded
    stdlib ``bz2`` module via ``tarfile.open(mode="r|bz2")``. The fallback
    caps COPY throughput at ~35 MB/s of compressed input on a modern laptop
    because ``bz2`` doesn't release the GIL — see CHANGELOG 2026-04-24.
    """
    tool = _parallel_bz2_tool()
    if tool is None:
        with tarfile.open(path, mode="r|bz2") as tf:
            yield tf
        return

    proc = subprocess.Popen(
        [tool, "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1 << 20,
    )
    assert proc.stdout is not None
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
            yield tf
    finally:
        proc.stdout.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def iter_mbdump_members(tar: tarfile.TarFile) -> Iterator[DumpMember]:
    """Yield each ``mbdump/<table>`` TSV as a readable file-like.

    ``tarfile.extractfile`` returns a stream valid only until the next
    ``next()`` call, so consumers MUST fully read each member before advancing.
    """
    for info in tar:
        if not info.isfile():
            continue
        parts = info.name.split("/")
        if len(parts) != 2 or parts[0] != "mbdump":
            continue
        fobj = tar.extractfile(info)
        if fobj is None:
            continue
        yield DumpMember(table_name=parts[1], size=info.size, file=fobj)


def read_metadata_file(path: Path, member_name: str) -> str | None:
    """Read a small top-level file (SCHEMA_SEQUENCE, TIMESTAMP, REPLICATION_SEQUENCE).

    Opens a separate streaming reader so it doesn't disturb the main import
    iterator. Uses stdlib ``bz2`` unconditionally — these files are a handful
    of bytes each, so the parallel-tool spin-up cost would exceed the decode.
    """
    with tarfile.open(path, mode="r|bz2") as tf:
        for info in tf:
            if info.name == member_name and info.isfile():
                fobj = tf.extractfile(info)
                if fobj is None:
                    return None
                return fobj.read().decode("utf-8", errors="replace").strip()
    return None
