from __future__ import annotations

from enum import StrEnum


class Phase(StrEnum):
    PRE = "pre"
    POST = "post"
    ALL = "all"


REQUIRED_EXTENSIONS = ("cube", "earthdistance", "unaccent")

# Note: historical versions of musicbrainz-server shipped a
# postgresql-extensions/ directory with C extensions named
# musicbrainz_collate / musicbrainz_unaccent. Upstream removed those —
# CreateCollations.sql now uses plain `provider = icu`, and
# musicbrainz_unaccent is a SQL function defined in Extensions.sql.
# So we only need the stock contrib extensions above plus an ICU-enabled
# server, which every official postgres:* image provides.

BOOKKEEPING_SCHEMA = "musicbrainz_database_setup"
APPLIED_PHASES_TABLE = "applied_phases"
IMPORTED_ARCHIVES_TABLE = "imported_archives"
