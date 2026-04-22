from __future__ import annotations

from enum import StrEnum


class Phase(StrEnum):
    PRE = "pre"
    POST = "post"
    ALL = "all"


REQUIRED_EXTENSIONS = ("cube", "earthdistance", "unaccent")

# Collations created by admin/sql/CreateCollations.sql depend on these
# operator-installed C extensions. We probe pg_available_extensions before
# running the SQL so the error points at PREREQUISITES.md, not at a cryptic
# CREATE COLLATION failure.
REQUIRED_COLLATION_EXTENSIONS = ("musicbrainz_collate", "musicbrainz_unaccent")

BOOKKEEPING_SCHEMA = "musicbrainz_db_setup"
APPLIED_PHASES_TABLE = "applied_phases"
IMPORTED_ARCHIVES_TABLE = "imported_archives"
