"""Test tarfile routing: only mbdump/<table> entries are yielded as DumpMembers."""

from __future__ import annotations

import bz2
import io
import shutil
import tarfile
from pathlib import Path

import pytest

from musicbrainz_database_setup.errors import ImportError_
from musicbrainz_database_setup.importer import archive as archive_module
from musicbrainz_database_setup.importer.archive import (
    iter_mbdump_members,
    open_archive,
    read_metadata_file,
)


def _make_archive(tmp_path: Path) -> Path:
    """Build a tiny bz2 tar with the structure a real MB dump uses."""
    archive_path = tmp_path / "mbdump.tar.bz2"

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        _add_file(tf, "SCHEMA_SEQUENCE", b"28\n")
        _add_file(tf, "TIMESTAMP", b"2026-04-08 00:22:12.000000+00\n")
        _add_file(tf, "REPLICATION_SEQUENCE", b"12345\n")
        _add_file(tf, "mbdump/artist", b"1\tArtist row\n")
        _add_file(tf, "mbdump/release", b"1\tRelease row\n")
        _add_file(tf, "COPYING", b"CC0\n")  # should NOT be yielded

    archive_path.write_bytes(bz2.compress(raw.getvalue()))
    return archive_path


def _add_file(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def test_iter_mbdump_members_only_yields_mbdump_files(tmp_path: Path):
    archive = _make_archive(tmp_path)
    with open_archive(archive) as tar:
        names = [m.table_name for m in iter_mbdump_members(tar)]
    assert set(names) == {"artist", "release"}


def test_iter_mbdump_members_exposes_size(tmp_path: Path):
    archive = _make_archive(tmp_path)
    with open_archive(archive) as tar:
        for member in iter_mbdump_members(tar):
            assert member.size > 0
            # MUST read before advancing — the stream is one-shot.
            data = member.file.read()
            assert data


def test_read_metadata_file_returns_stripped_text(tmp_path: Path):
    archive = _make_archive(tmp_path)
    assert read_metadata_file(archive, "SCHEMA_SEQUENCE") == "28"
    assert read_metadata_file(archive, "REPLICATION_SEQUENCE") == "12345"
    assert read_metadata_file(archive, "DOES_NOT_EXIST") is None


def test_open_archive_falls_back_to_stdlib_when_no_parallel_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Without pbzip2/lbzip2 on PATH, open_archive uses CPython stdlib bz2."""
    monkeypatch.setattr(archive_module, "_parallel_bz2_tool", lambda: None)
    archive = _make_archive(tmp_path)
    with open_archive(archive) as tar:
        names = [m.table_name for m in iter_mbdump_members(tar)]
    assert set(names) == {"artist", "release"}


def test_open_archive_uses_subprocess_pipe_when_tool_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """With a parallel bz2 tool available, open_archive pipes through it.

    Uses plain `bzip2 -dc` as a stand-in for pbzip2 — same CLI contract.
    Skips on machines without a `bzip2` binary.
    """
    bzip2 = shutil.which("bzip2")
    if bzip2 is None:
        pytest.skip("bzip2 binary not available on this machine")
    monkeypatch.setattr(archive_module, "_parallel_bz2_tool", lambda: bzip2)
    archive = _make_archive(tmp_path)
    with open_archive(archive) as tar:
        members = {m.table_name: m.file.read() for m in iter_mbdump_members(tar)}
    assert set(members) == {"artist", "release"}
    assert members["artist"] == b"1\tArtist row\n"
    assert members["release"] == b"1\tRelease row\n"


def test_parallel_bz2_tool_prefers_pbzip2_over_lbzip2(monkeypatch: pytest.MonkeyPatch):
    """Shutil.which probing order is pbzip2 first, lbzip2 as fallback."""
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        if name == "pbzip2":
            return "/usr/local/bin/pbzip2"
        return None

    monkeypatch.setattr(archive_module.shutil, "which", fake_which)
    assert archive_module._parallel_bz2_tool() == "/usr/local/bin/pbzip2"
    assert calls == ["pbzip2"]  # short-circuits before checking lbzip2


def _fake_failing_bz2_tool(tmp_path: Path, *, source_bzip2: str) -> Path:
    """Write a tiny shell script that honours the ``<tool> -dc <path>``
    contract — decompresses the input via real `bzip2 -dc` so `tarfile`
    sees a valid stream — then exits 2 with a stderr message, simulating
    a parallel decompressor that flags a late failure (e.g. a CRC
    mismatch reported after emitting a valid prefix).
    """
    script = tmp_path / "fake_failing_bzip2"
    script.write_text(
        "#!/bin/sh\n"
        f'{source_bzip2} -dc "$2"\n'
        'echo "simulated late decompressor failure" >&2\n'
        "exit 2\n"
    )
    script.chmod(0o755)
    return script


def test_open_archive_raises_when_parallel_tool_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A non-zero exit from the parallel decompressor must surface.

    Reproduces the PR review finding: a decompressor that exits non-zero
    after producing a tar stream `tarfile.open(mode="r|")` reads to
    completion would otherwise be treated as a successful import. We use
    a shell-script stand-in that emits a valid decompressed stream and
    then exits 2, so tar iteration completes cleanly and the post-loop
    subprocess-status check is the one that fires.
    """
    bzip2 = shutil.which("bzip2")
    if bzip2 is None:
        pytest.skip("bzip2 binary not available on this machine")
    fake_tool = _fake_failing_bz2_tool(tmp_path, source_bzip2=bzip2)
    monkeypatch.setattr(archive_module, "_parallel_bz2_tool", lambda: str(fake_tool))

    archive = _make_archive(tmp_path)

    with pytest.raises(ImportError_, match="exited with status 2"), open_archive(archive) as tar:
        # Exhaust the iterator so clean_exit flips True and the
        # returncode check fires on __exit__.
        for m in iter_mbdump_members(tar):
            m.file.read()


def test_open_archive_does_not_mask_consumer_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """If the consumer raises mid-iteration, that exception propagates —
    the subprocess's SIGPIPE-induced non-zero exit during teardown must
    not mask the actionable root cause.
    """
    bzip2 = shutil.which("bzip2")
    if bzip2 is None:
        pytest.skip("bzip2 binary not available on this machine")
    monkeypatch.setattr(archive_module, "_parallel_bz2_tool", lambda: bzip2)

    archive = _make_archive(tmp_path)

    class ConsumerFault(Exception):
        pass

    with pytest.raises(ConsumerFault), open_archive(archive) as tar:
        for _m in iter_mbdump_members(tar):
            raise ConsumerFault("simulated COPY failure")
