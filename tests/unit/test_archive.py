"""Test tarfile routing: only mbdump/<table> entries are yielded as DumpMembers."""

from __future__ import annotations

import bz2
import io
import tarfile
from pathlib import Path

from musicbrainz_db_setup.importer.archive import (
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
