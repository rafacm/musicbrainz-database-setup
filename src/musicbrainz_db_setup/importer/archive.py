"""Iterate TSV members of a MusicBrainz dump archive without extracting to disk."""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass(slots=True)
class DumpMember:
    table_name: str  # last path component of mbdump/<table>
    size: int
    file: IO[bytes]


@contextmanager
def open_archive(path: Path) -> Iterator[tarfile.TarFile]:
    """Open a tar.bz2 in pure streaming mode ("r|bz2")."""
    with tarfile.open(path, mode="r|bz2") as tf:
        yield tf


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
    iterator.
    """
    with tarfile.open(path, mode="r|bz2") as tf:
        for info in tf:
            if info.name == member_name and info.isfile():
                fobj = tf.extractfile(info)
                if fobj is None:
                    return None
                return fobj.read().decode("utf-8", errors="replace").strip()
    return None
