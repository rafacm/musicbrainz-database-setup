"""Iterate TSV members of a MusicBrainz dump archive without extracting to disk."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tarfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from musicbrainz_database_setup.errors import ImportError_

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

    Raises ``ImportError_`` if the decompressor exits non-zero *and* the
    caller iterated the tar to completion without raising — this catches
    truncated / corrupt archives where ``tarfile.open(mode="r|")`` would
    otherwise silently stop mid-stream and ``import_archive()`` would
    happily record a partial import. When the caller raises first (broken
    tar, COPY failure, SIGINT), the original exception propagates; a
    SIGPIPE-induced non-zero exit from the decompressor during teardown
    is not the actionable root cause.
    """
    tool = _parallel_bz2_tool()
    if tool is None:
        with tarfile.open(path, mode="r|bz2") as tf:
            yield tf
        return

    proc = subprocess.Popen(
        [tool, "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1 << 20,
    )
    # Hoist out of Optional so the closure below sees a concrete IO[bytes].
    stdout_pipe = proc.stdout
    stderr_pipe = proc.stderr
    assert stdout_pipe is not None
    assert stderr_pipe is not None

    # Drain stderr on a background thread for the subprocess's whole
    # lifetime. If pbzip2 emits more than ~64 KB of stderr (unlikely but
    # possible on a badly-broken archive) and we only read it after
    # stdout EOF, the write side fills, pbzip2 blocks, and stdout never
    # reaches EOF — classic pipe deadlock. The thread + list-append
    # pattern is simpler than threading primitives and safe because
    # ``list.append`` is atomic under the GIL.
    stderr_chunks: list[bytes] = []

    def _drain_stderr() -> None:
        for chunk in iter(lambda: stderr_pipe.read(4096), b""):
            stderr_chunks.append(chunk)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    clean_exit = False
    try:
        with tarfile.open(fileobj=stdout_pipe, mode="r|") as tf:
            yield tf
        clean_exit = True
    finally:
        stdout_pipe.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stderr_thread.join(timeout=5)
        stderr_pipe.close()

        if clean_exit and proc.returncode != 0:
            stderr_text = (
                b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
                or "(no stderr)"
            )
            raise ImportError_(
                f"{tool} exited with status {proc.returncode} while "
                f"decompressing {path.name}: {stderr_text}"
            )


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
