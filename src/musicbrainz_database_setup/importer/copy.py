"""Stream TSV archive members into PostgreSQL via COPY FROM STDIN."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import IO

from psycopg import Connection, sql

from musicbrainz_database_setup.db import bulk_session
from musicbrainz_database_setup.errors import ImportError_
from musicbrainz_database_setup.importer.archive import (
    DumpMember,
    iter_mbdump_members,
    open_archive,
    read_metadata_file,
)
from musicbrainz_database_setup.importer.tables import schema_for_archive
from musicbrainz_database_setup.progress import ProgressManager
from musicbrainz_database_setup.schema.phases import (
    BOOKKEEPING_SCHEMA,
    IMPORTED_ARCHIVES_TABLE,
)
from musicbrainz_database_setup.ui.phases import format_elapsed, format_size

log = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 MiB


def ensure_bookkeeping(conn: Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(BOOKKEEPING_SCHEMA))
        )
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {}.{} (
                    archive_name TEXT PRIMARY KEY,
                    schema_sequence INT,
                    replication_sequence TEXT,
                    finished_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ).format(
                sql.Identifier(BOOKKEEPING_SCHEMA),
                sql.Identifier(IMPORTED_ARCHIVES_TABLE),
            )
        )
    conn.commit()


def already_imported(conn: Connection, archive_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT 1 FROM {}.{} WHERE archive_name = %s").format(
                sql.Identifier(BOOKKEEPING_SCHEMA),
                sql.Identifier(IMPORTED_ARCHIVES_TABLE),
            ),
            (archive_name,),
        )
        return cur.fetchone() is not None


def import_archive(
    conn: Connection,
    archive_path: Path,
    *,
    force: bool = False,
    index: int = 1,
    total: int = 1,
) -> None:
    """Import one MusicBrainz dump archive in a single transaction."""
    archive_name = archive_path.name
    schema_name = schema_for_archive(archive_name)
    ensure_bookkeeping(conn)

    if not force and already_imported(conn, archive_name):
        log.info(
            "(%d/%d) Archive %s already imported — skipping.",
            index,
            total,
            archive_name,
        )
        return

    schema_seq = read_metadata_file(archive_path, "SCHEMA_SEQUENCE")
    replication_seq = read_metadata_file(archive_path, "REPLICATION_SEQUENCE")

    log.info("(%d/%d) Importing tables from %s", index, total, archive_name)
    start = time.monotonic()
    tables_total = 0
    try:
        with bulk_session(conn):
            with open_archive(archive_path) as tar:
                for member in iter_mbdump_members(tar):
                    _copy_member(conn, member, schema_name)
                    tables_total += 1
            _record_imported(conn, archive_name, schema_seq, replication_seq)
            conn.commit()
    except Exception as exc:
        conn.rollback()
        raise ImportError_(f"Import of {archive_name} failed: {exc}") from exc
    log.info(
        "✓ (%d/%d) Imported %s · %d tables · %s",
        index,
        total,
        archive_name,
        tables_total,
        format_elapsed(time.monotonic() - start),
    )


def _copy_member(
    conn: Connection,
    member: DumpMember,
    schema_name: str,
) -> None:
    pm = ProgressManager.instance()
    table_task = pm.add_task(
        f"COPY {schema_name}.{member.table_name}",
        total=float(member.size) if member.size > 0 else None,
    )
    stmt = sql.SQL("COPY {}.{} FROM STDIN").format(
        sql.Identifier(schema_name), sql.Identifier(member.table_name)
    )
    try:
        with conn.cursor() as cur, cur.copy(stmt) as copy:
            _stream_into_copy(member.file, copy, table_task)
    finally:
        pm.remove_task(table_task)
    log.info(
        "✓ Table %s.%s · %s",
        schema_name,
        member.table_name,
        format_size(member.size) if member.size > 0 else "0 B",
    )


def _stream_into_copy(src: IO[bytes], copy: object, task_id: object) -> None:
    pm = ProgressManager.instance()
    write = copy.write  # type: ignore[attr-defined]
    while True:
        chunk = src.read(_CHUNK)
        if not chunk:
            break
        write(chunk)
        pm.advance(task_id, len(chunk))  # type: ignore[arg-type]


def _record_imported(
    conn: Connection,
    archive_name: str,
    schema_seq: str | None,
    replication_seq: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                INSERT INTO {}.{} (archive_name, schema_sequence, replication_sequence)
                VALUES (%s, %s, %s)
                ON CONFLICT (archive_name) DO UPDATE
                SET schema_sequence = EXCLUDED.schema_sequence,
                    replication_sequence = EXCLUDED.replication_sequence,
                    finished_at = now()
                """
            ).format(
                sql.Identifier(BOOKKEEPING_SCHEMA),
                sql.Identifier(IMPORTED_ARCHIVES_TABLE),
            ),
            (
                archive_name,
                int(schema_seq) if schema_seq and schema_seq.isdigit() else None,
                replication_seq,
            ),
        )
