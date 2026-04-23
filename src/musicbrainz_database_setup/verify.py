from __future__ import annotations

import logging
from pathlib import Path

from musicbrainz_database_setup.importer.archive import read_metadata_file

log = logging.getLogger(__name__)


def read_schema_sequence(archive_path: Path) -> int | None:
    raw = read_metadata_file(archive_path, "SCHEMA_SEQUENCE")
    if raw and raw.isdigit():
        return int(raw)
    return None


def read_replication_sequence(archive_path: Path) -> str | None:
    return read_metadata_file(archive_path, "REPLICATION_SEQUENCE")
