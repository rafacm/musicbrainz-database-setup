from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from musicbrainz_database_setup.errors import UserError


def connect(db_url: str | None, *, autocommit: bool = False) -> Connection:
    if not db_url:
        raise UserError(
            "No database URL. Pass --db or set MUSICBRAINZ_DATABASE_SETUP_DB_URL "
            "(e.g. postgresql://user:pass@host:5432/dbname)."
        )
    return psycopg.connect(db_url, autocommit=autocommit)


@contextmanager
def bulk_session(conn: Connection) -> Iterator[Connection]:
    """Session-scoped tuning for bulk COPY. Settings revert on reset."""
    # psycopg3 refuses to assign `autocommit` (even to the same value) unless
    # the connection is IDLE. Callers may have opened an implicit transaction
    # with a prior SELECT probe, so only flip the attribute if it needs to
    # change.
    prior_autocommit = conn.autocommit
    if prior_autocommit:
        conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET LOCAL synchronous_commit = off")
        cur.execute("SET LOCAL maintenance_work_mem = '2GB'")
        cur.execute("SET LOCAL work_mem = '256MB'")
        cur.execute("SET LOCAL statement_timeout = 0")
    try:
        yield conn
    finally:
        if prior_autocommit and not conn.autocommit:
            conn.autocommit = True


def role_is_superuser(conn: Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('is_superuser')::bool")
        row = cur.fetchone()
        return bool(row and row[0])


def server_major_version(conn: Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SHOW server_version_num")
        row = cur.fetchone()
        assert row is not None
        return int(row[0]) // 10000
