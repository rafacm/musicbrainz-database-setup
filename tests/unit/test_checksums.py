from pathlib import Path

import pytest

from musicbrainz_db_setup.errors import ChecksumError
from musicbrainz_db_setup.mirror.checksums import (
    hash_file,
    parse,
    verify_file,
)

SHA256SUMS_FIXTURE = """\
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  mbdump.tar.bz2
# a comment
9e107d9d372bb6826bd81d3542a419d6  mbdump-derived.tar.bz2
"""


def test_parse_sha256sums_extracts_entries():
    cs = parse(SHA256SUMS_FIXTURE, algo="sha256")
    assert cs.algo == "sha256"
    assert cs.entries["mbdump.tar.bz2"].startswith("e3b0c44298")
    assert "mbdump-derived.tar.bz2" in cs.entries  # MD5 line is still parsed


def test_parse_ignores_blank_and_malformed_lines():
    cs = parse("\n\nnot-a-real-line\n", algo="sha256")
    assert cs.entries == {}


def test_verify_file_matches(tmp_path: Path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    verify_file(f, digest, "sha256")  # no raise


def test_verify_file_mismatch_raises(tmp_path: Path):
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    with pytest.raises(ChecksumError):
        verify_file(f, "deadbeef" * 8, "sha256")


def test_hash_file_md5(tmp_path: Path):
    f = tmp_path / "hello.txt"
    f.write_bytes(b"hello")
    assert hash_file(f, "md5") == "5d41402abc4b2a76b9719d911017c592"
