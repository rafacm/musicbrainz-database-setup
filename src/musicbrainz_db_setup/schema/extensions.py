from __future__ import annotations

import logging

from psycopg import Connection, sql

from musicbrainz_db_setup.errors import PrerequisiteMissing
from musicbrainz_db_setup.schema.phases import (
    REQUIRED_COLLATION_EXTENSIONS,
    REQUIRED_EXTENSIONS,
)

log = logging.getLogger(__name__)


def available_extensions(conn: Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM pg_available_extensions")
        return {row[0] for row in cur.fetchall()}


def preflight(conn: Connection) -> None:
    available = available_extensions(conn)
    missing_required = [e for e in REQUIRED_EXTENSIONS if e not in available]
    if missing_required:
        raise PrerequisiteMissing(
            "Missing PostgreSQL extensions: "
            + ", ".join(missing_required)
            + ". Install 'postgresql-contrib' (or your distro's equivalent) on the server."
        )
    missing_collation = [e for e in REQUIRED_COLLATION_EXTENSIONS if e not in available]
    if missing_collation:
        raise PrerequisiteMissing(
            "Missing MusicBrainz custom extensions: "
            + ", ".join(missing_collation)
            + ". See docs/PREREQUISITES.md for build instructions."
        )


def ensure_extensions(conn: Connection) -> None:
    with conn.cursor() as cur:
        for ext in REQUIRED_EXTENSIONS:
            cur.execute(
                sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext))
            )
            log.debug("Ensured extension %s", ext)
