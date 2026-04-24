"""Runs schema DDL phases in the canonical InitDb.pl order.

Each upstream ``admin/sql/*.sql`` file is applied by shelling out to
``psql`` (matching what ``admin/InitDb.pl`` does), because these files
use psql-specific meta-commands (``\\set ON_ERROR_STOP 1``, ``\\unset``)
and manage their own ``BEGIN;/COMMIT;`` pairs. Our own bookkeeping
runs via psycopg3 on a separate transaction so completed phases are
recorded in ``musicbrainz_database_setup.applied_phases`` and reruns
are idempotent.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from psycopg import Connection, sql

from musicbrainz_database_setup.schema.extensions import preflight
from musicbrainz_database_setup.schema.phases import (
    APPLIED_PHASES_TABLE,
    BOOKKEEPING_SCHEMA,
    Phase,
)
from musicbrainz_database_setup.schema.psql import ensure_psql_available, run_sql_file
from musicbrainz_database_setup.sql import github, manifest
from musicbrainz_database_setup.sql.manifest import SqlFile

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        conn: Connection,
        *,
        sha: str,
        modules: tuple[str, ...],
        cache_root: Path | None = None,
    ) -> None:
        self.conn = conn
        self.sha = sha
        self.modules = modules
        self.cache_root = cache_root

    # ------------------------------------------------------------------ setup

    def ensure_bookkeeping(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(BOOKKEEPING_SCHEMA)
                )
            )
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {}.{} (
                        phase TEXT PRIMARY KEY,
                        sha TEXT NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                ).format(
                    sql.Identifier(BOOKKEEPING_SCHEMA),
                    sql.Identifier(APPLIED_PHASES_TABLE),
                )
            )
        self.conn.commit()

    def ensure_schemas(self) -> None:
        with self.conn.cursor() as cur:
            for schema in manifest.required_schemas(self.modules):
                cur.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
                )
                log.debug("Ensured schema %s", schema)
        self.conn.commit()

    # ---------------------------------------------------------------- phases

    def run_pre_import(self) -> None:
        ensure_psql_available()
        preflight(self.conn)
        self.ensure_bookkeeping()
        self.ensure_schemas()
        self.conn.commit()

        for sqlfile in manifest.pre_import_files(self.modules):
            self._run_file(sqlfile, phase_group="pre")

    def run_post_import(self) -> None:
        ensure_psql_available()
        self.ensure_bookkeeping()
        for sqlfile in manifest.post_import_files(self.modules):
            self._run_file(sqlfile, phase_group="post")

    def run(self, phase: Phase) -> None:
        if phase in (Phase.PRE, Phase.ALL):
            self.run_pre_import()
        if phase in (Phase.POST, Phase.ALL):
            self.run_post_import()

    # -------------------------------------------------------------- internals

    def _run_file(self, sqlfile: SqlFile, *, phase_group: str) -> None:
        phase_key = f"{phase_group}:{sqlfile.repo_path}"
        if self._already_applied(phase_key):
            log.info("Skipping %s (already applied)", phase_key)
            return

        local = github.fetch(sqlfile.repo_path, sha=self.sha, cache_root=self.cache_root)
        log.info("Running %s", sqlfile.repo_path)

        # psql manages the file's own BEGIN;/COMMIT; and handles meta-commands
        # natively. Release any read txn left open by _already_applied first
        # so psql's connection sees a clean state.
        self.conn.commit()
        start = time.monotonic()
        run_sql_file(self.conn, local)
        log.info("%s finished in %.1fs", sqlfile.repo_path, time.monotonic() - start)

        # Record applied-phase bookkeeping in its own small transaction.
        self._record_applied(phase_key)
        self.conn.commit()

    def _already_applied(self, phase_key: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT 1 FROM {}.{} WHERE phase = %s").format(
                    sql.Identifier(BOOKKEEPING_SCHEMA),
                    sql.Identifier(APPLIED_PHASES_TABLE),
                ),
                (phase_key,),
            )
            return cur.fetchone() is not None

    def _record_applied(self, phase_key: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "INSERT INTO {}.{} (phase, sha) VALUES (%s, %s) "
                    "ON CONFLICT (phase) DO UPDATE SET sha = EXCLUDED.sha, applied_at = now()"
                ).format(
                    sql.Identifier(BOOKKEEPING_SCHEMA),
                    sql.Identifier(APPLIED_PHASES_TABLE),
                ),
                (phase_key, self.sha),
            )
