import pytest

from musicbrainz_db_setup.importer.tables import (
    module_for_archive,
    schema_for_archive,
)


def test_schema_for_core_archive():
    assert schema_for_archive("mbdump.tar.bz2") == "musicbrainz"


def test_schema_for_cover_art():
    assert schema_for_archive("mbdump-cover-art-archive.tar.bz2") == "cover_art_archive"


def test_module_lookup_roundtrip():
    assert module_for_archive("mbdump-stats.tar.bz2") == "stats"


def test_unknown_archive_raises():
    with pytest.raises(ValueError):
        schema_for_archive("nope.tar.bz2")
