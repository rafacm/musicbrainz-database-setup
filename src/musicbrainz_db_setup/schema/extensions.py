from __future__ import annotations

import logging

from psycopg import Connection, sql

from musicbrainz_db_setup.errors import PrerequisiteMissing
from musicbrainz_db_setup.schema.phases import REQUIRED_EXTENSIONS

log = logging.getLogger(__name__)


def available_extensions(conn: Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM pg_available_extensions")
        return {row[0] for row in cur.fetchall()}


def server_supports_icu(conn: Connection) -> bool:
    """Return True if the PG build has ICU support.

    CreateCollations.sql now defines ``musicbrainz`` via ``provider = icu``,
    so the server must have been built with --with-icu. The official
    postgres images (both Debian and Alpine variants) have shipped with
    ICU enabled since PG 16, but managed / self-compiled servers may not.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_collation WHERE collprovider = 'i'")
        row = cur.fetchone()
        return bool(row and row[0] > 0)


def preflight(conn: Connection) -> None:
    available = available_extensions(conn)
    missing = [e for e in REQUIRED_EXTENSIONS if e not in available]
    if missing:
        raise PrerequisiteMissing(
            "Missing PostgreSQL extensions: "
            + ", ".join(missing)
            + ". Install 'postgresql-contrib' (or your distro's equivalent) "
            "on the server. The official postgres:* images include it."
        )
    if not server_supports_icu(conn):
        raise PrerequisiteMissing(
            "PostgreSQL was not built with ICU support, but "
            "admin/sql/CreateCollations.sql requires a `provider = icu` "
            "collation. Use an image built with --with-icu (all official "
            "postgres:* images since PG 16 qualify)."
        )


def ensure_extensions(conn: Connection) -> None:
    with conn.cursor() as cur:
        for ext in REQUIRED_EXTENSIONS:
            cur.execute(
                sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext))
            )
            log.debug("Ensured extension %s", ext)
