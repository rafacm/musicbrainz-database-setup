"""Runs schema DDL phases in the canonical InitDb.pl order.

Each SQL file is executed in its own transaction. Completed phases are
recorded in ``musicbrainz_db_setup.applied_phases`` so reruns are idempotent.
"""

from __future__ import annotations

import logging
from pathlib import Path

from psycopg import Connection, sql

from musicbrainz_db_setup.errors import SchemaError
from musicbrainz_db_setup.schema.extensions import ensure_extensions, preflight
from musicbrainz_db_setup.schema.phases import (
    APPLIED_PHASES_TABLE,
    BOOKKEEPING_SCHEMA,
    Phase,
)
from musicbrainz_db_setup.sql import github, manifest
from musicbrainz_db_setup.sql.manifest import SqlFile

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
        preflight(self.conn)
        self.ensure_bookkeeping()
        self.ensure_schemas()
        ensure_extensions(self.conn)
        self.conn.commit()

        for sqlfile in manifest.pre_import_files(self.modules):
            self._run_file(sqlfile, phase_group="pre")

    def run_post_import(self) -> None:
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
        body = local.read_text(encoding="utf-8")
        log.info("Running %s", sqlfile.repo_path)
        try:
            with self.conn.cursor() as cur:
                cur.execute(body)  # type: ignore[arg-type]
            self._record_applied(phase_key)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            raise SchemaError(f"Failed to apply {sqlfile.repo_path}: {exc}") from exc

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
