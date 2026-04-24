# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), using dates (`## YYYY-MM-DD`) as section headers instead of version numbers.

## 2026-04-24

### Changed

- `schema.psql._PGOPTIONS` now applies the same session-tuning knobs as `db.bulk_session()` (`synchronous_commit=off`, `maintenance_work_mem=1GB`, `work_mem=256MB`, `max_parallel_maintenance_workers=4`, `statement_timeout=0`) to every `admin/sql/*.sql` `psql` invocation. `bulk_session()` only wraps the COPY transaction (a psycopg3 path), so without this change the post-import DDL files ran on stock 64 MB `maintenance_work_mem` and `synchronous_commit=on`, which dominated total import time. Plan: [`docs/plans/2026-04-24-faster-import.md`](docs/plans/2026-04-24-faster-import.md). Feature doc: [`docs/features/2026-04-24-faster-import.md`](docs/features/2026-04-24-faster-import.md). Sessions: [planning](docs/sessions/2026-04-24-faster-import-planning-session.md), [implementation](docs/sessions/2026-04-24-faster-import-implementation-session.md).
- Restructured the root `README.md`: project-identity image at the top, less-technical opening paragraph and more-positive second paragraph, TL;DR-first Requirements (full details moved to a new "Requirements in detail" section linked from the TL;DR), Quick-start numbered list replaced with sub-sections and multi-line `docker` / `uv` commands, Modules table slimmed (dropped the redundant Archive column), "Commands" renamed to "Supported commands" with a `--help` pointer, and "What's already implemented" condensed from ten bullets to five. Configuration table rows for `SQL_REF`, `WORKDIR`, `MODULES` now include their defaults, plus a new row for `SQL_CACHE_DIR`.
- Modules section: removed the Licence column (the linked [MusicBrainz Database / Download wiki page](https://wiki.musicbrainz.org/MusicBrainz_Database/Download) is the canonical source for per-archive licensing) and rewrote the Contents cells using the wiki's own wording — surfacing non-obvious bits the old one-liners hid (genres-via-tags in `derived`, the editor FK dependency, "metadata only — no images" for the art archives, the actual `wikidocs_index` table name, etc.). Moved the wiki pointer and `--modules` example to the section intro.

### Added

- `importer.archive.open_archive()` now detects `pbzip2` / `lbzip2` on `$PATH` and pipes the `.tar.bz2` through it for parallel decompression when available; falls back to CPython's stdlib `bz2` transparently when neither is installed. Live monitoring of a fresh core-module import showed Python pinned at 100 % CPU on one core during the entire COPY phase while the Postgres backend sat on `wait_event=Client/ClientRead` — the stdlib `bz2` module is single-threaded (no GIL release) and became the ceiling on COPY throughput. New tests cover both code paths: `tests/unit/test_archive.py::test_open_archive_falls_back_to_stdlib_when_no_parallel_tool` and `test_open_archive_uses_subprocess_pipe_when_tool_present` (uses `bzip2 -dc` as a stand-in when pbzip2 is absent, since the CLI contract matches). Plan: [`docs/plans/2026-04-24-faster-import.md`](docs/plans/2026-04-24-faster-import.md). Feature doc: [`docs/features/2026-04-24-faster-import.md`](docs/features/2026-04-24-faster-import.md). Sessions: [planning](docs/sessions/2026-04-24-faster-import-planning-session.md), [implementation](docs/sessions/2026-04-24-faster-import-implementation-session.md).
- `schema.orchestrator.Orchestrator._run_file()` now logs `<phase> finished in <elapsed>s` per `admin/sql/*.sql` file, so slow phases show their cost inline in the transcript without consulting `musicbrainz_database_setup.applied_phases`.
- README `Requirements` gains a brief `pbzip2` / `lbzip2` bullet; `Requirements in detail` adds a paragraph explaining why CPython's `bz2` is the COPY-phase ceiling and how to install a parallel alternative, plus an "optional server-side tuning" `docker run` example with `shared_buffers`, `max_wal_size`, `checkpoint_timeout`, `effective_io_concurrency`, `random_page_cost` flags that must be set at server start (i.e. can't be pushed through `PGOPTIONS`).
- `tests/unit/test_psql_env.py::test_psql_env_pgoptions_includes_ddl_performance_knobs` + `test_pgoptions_constant_matches_psql_env_output` — regressions that pin the new `_PGOPTIONS` content so a future accidental revert surfaces immediately.
- New "Splitting the connection string" sub-section under Configuration documents the libpq `PG*` env-var fallback pattern — e.g. `PGPASSWORD` supplied at runtime from a secret manager while host/port/user/database stay committed in `.env`.
- `tests/unit/test_psql_env.py`: three unit tests covering `schema.psql._psql_env` — `PGPASSWORD` set from a password-bearing URL, passwordless URL leaves an inherited `PGPASSWORD` intact, and both-absent leaves `PGPASSWORD` out of the child env.
- AGENTS.md rule: whenever a CLI command is added, renamed, removed, or its behaviour changes, the whole documentation surface must be reviewed (README sections beyond "Supported commands", `docs/features/`, AGENTS.md itself).
- GitHub Actions CI workflow at `.github/workflows/ci.yml`: runs `ruff` → `mypy` → `pytest` under `uv sync --extra dev` on pushes to `main` and PRs into `main`. Matrix over Python 3.11 / 3.12 / 3.13 with `fail-fast: false`; a `concurrency` group cancels superseded PR runs to save Actions minutes.
- README header badges (centered `<p>` below the tagline): CI status linking to the Actions runs page, supported Python versions (3.11 | 3.12 | 3.13), and MIT license.
- README third intro paragraph noting this project came out of [RAGtime](https://github.com/rafacm/ragtime), where it stands up the local MusicBrainz mirror used by the [entity-resolution step](https://github.com/rafacm/ragtime/tree/main/doc#8--resolve-entities-status-resolving).

### Removed

- `## Scope` section in the README. The "one-shot full imports only" line was already captured in AGENTS.md's "Out of scope for v1" list; the SQL-ref reproducibility tip ("pin to a `v-NN-schema-change` tag") moved into the Configuration table's `SQL_REF` row.

### Fixed

- OOM on an 8 GB Docker Desktop VM during `CreateFKConstraints.sql` when the tuned settings combined `shared_buffers=4GB` + `_PGOPTIONS maintenance_work_mem=2GB`: worst-case ask was 4 GB shared + 5 × 2 GB = 14 GB on a single CREATE INDEX. Lowered `_PGOPTIONS maintenance_work_mem` from `2GB` → `1GB` (peak 5 GB) and the README's tuned `docker run` `shared_buffers` from `4GB` → `2GB` (25 % of an 8 GB VM). Added a `⚠️ Memory sizing` callout in the README explaining the `1 + max_parallel_maintenance_workers` multiplier. End-to-end tuned run now completes in 20 m 44 s vs 26 m 53 s untuned (−23 %) — COPY 14 m 01 s → 7 m 17 s (−48 %, pbzip2 working as designed), CreateIndexes 4 m 05 s → 3 m 00 s (−27 %, parallel maintenance workers).
- Seven `mypy --strict` errors in `src/musicbrainz_database_setup/cli.py` and `src/musicbrainz_database_setup/progress.py`: typed the kwargs bag in `ProgressManager.update` as `dict[str, Any]` so `**unpack` reaches `rich.progress.Progress.update`'s heterogeneously-typed params; added narrow `# type: ignore[assignment]` on the two Typer `= ...` required-option defaults in `cli.import_` and `cli.verify_cmd` (idiom mypy can't model); annotated `cli._handle_errors() -> Iterator[None]`.

## 2026-04-22

### Added

- Initial implementation of the `musicbrainz-database-setup` CLI — downloads MusicBrainz dump archives, creates the schema (by fetching `admin/sql/*.sql` from `metabrainz/musicbrainz-server` at a configurable git ref), and streams the TSVs into `COPY FROM STDIN`. Plan: [`docs/plans/2026-04-22-initial-implementation.md`](docs/plans/2026-04-22-initial-implementation.md). Feature doc: [`docs/features/2026-04-22-initial-implementation.md`](docs/features/2026-04-22-initial-implementation.md). Sessions: [planning](docs/sessions/2026-04-22-initial-implementation-planning-session.md), [implementation](docs/sessions/2026-04-22-initial-implementation-implementation-session.md).

### Changed

- Renamed `docs/PREREQUISITES.md` → `docs/README.md` and rewrote the "PostgreSQL server" section to lead with the Docker image shipped in `tests/docker/` (build, `docker run`, use the entrypoint-created `postgres` superuser, or optionally create a dedicated `mb` superuser). The manual "compile extensions on the PG host" instructions are preserved as a secondary "Pointing at a pre-existing PostgreSQL server" sub-section.

## 2026-04-23

### Added

- Indeterminate spinner + elapsed-time ticker for each `admin/sql/*.sql` file, so long-running phases (`CreateIndexes.sql`, `CreateFKConstraints.sql`, …) don't look frozen during real-mirror imports. `schema/psql.run_sql_file()` registers a per-file task with `ProgressManager` around the `psql` subprocess and removes it when the process returns. `cli.schema_create` and `cli.run` now wrap their whole body in `progress_session()` so the live display is active across the pre-import and post-import phases (not just the COPY loop). `TimeElapsedColumn` added to the shared `Progress` column set. A real %-progress bar would need to poll `pg_stat_progress_create_index` / `pg_stat_progress_vacuum` on a second connection — deferred to a follow-up PR.

### Removed

- Deleted `tests/docker/Dockerfile`. Upstream `musicbrainz-server` removed the `postgresql-extensions/` directory — `CreateCollations.sql` is now a plain ICU collation (`CREATE COLLATION ... provider = icu`) and `musicbrainz_unaccent` is a SQL function defined inline in `Extensions.sql`. No custom PG build is required; any official `postgres:*` image works (including `postgres:17-alpine`).
- Removed `REQUIRED_COLLATION_EXTENSIONS` from `schema/phases.py` and the matching preflight check in `schema/extensions.py`.

### Changed

- `schema/extensions.preflight()` now probes `pg_collation` for ICU support (via `collprovider = 'i'`) instead of looking for `musicbrainz_collate` / `musicbrainz_unaccent` extensions.
- Rewrote `docs/README.md` around vanilla `postgres:*` images — including an `image: postgres:17-alpine` snippet for projects that already have a docker-compose.yml. Added a note on managed Postgres (RDS, Cloud SQL).
- Renamed the project end-to-end from `musicbrainz-db-setup` → `musicbrainz-database-setup` for SEO and CLI/package/repo consistency. Affected: Python module (`musicbrainz_db_setup` → `musicbrainz_database_setup`), PyPI package, CLI entrypoint, env-var prefix (`MUSICBRAINZ_DB_SETUP_*` → `MUSICBRAINZ_DATABASE_SETUP_*`), bookkeeping PG schema (`musicbrainz_db_setup` → `musicbrainz_database_setup`), XDG cache paths, and the GitHub repo itself. Verbatim user messages from prior session transcripts were preserved.
- Rewrote the root `README.md`: direct opening paragraph stating what the tool is, a `Requirements` section that cites upstream sources (`Extensions.sql`, `CreateCollations.sql`, the `postgres` Docker image), a Quick start that boots `postgres:17-alpine` and imports the `core` module in three commands, a full `Modules` table with archive / target schema / contents / licence, and a `References` section linking to every primary source this tool is built on.

### Removed

- Deleted `docs/README.md`. Its content (PG requirements, docker-compose snippet, managed-PG note, disk sizing) folded into the root `README.md` where it belongs alongside the Quick start — one README is clearer than two for prerequisites.

### Added

- `LICENSE` file at the repo root (MIT, © 2026 Rafael Cordones). Matches the existing `pyproject.toml` declaration and brings this project in line with the rest of the MB tooling layer (`mbdata`, `mbslave`, `musicbrainz-docker` are all MIT). `pyproject.toml` now points at the file via `license = { file = "LICENSE" }`.
- New `Status` section in `README.md` with "What's already implemented" (bulleted summary of shipped functionality) and "What's coming" (`SCHEMA_SEQUENCE` cross-check, canary CI for upstream phase-file drift, pre-built GHCR runner image).

### Fixed

- Schema orchestrator failed on the very first SQL file with `syntax error at or near "\"` because the upstream `admin/sql/*.sql` files are psql-flavoured (start with `\set ON_ERROR_STOP 1`, wrap themselves in `BEGIN;/COMMIT;`) and we were handing them to psycopg3 directly. New `schema/psql.py` shells out to `psql -f <file>` using credentials extracted from the psycopg connection — matching what `admin/InitDb.pl` does upstream. `psql` is now a documented client-machine requirement and `schema.psql.ensure_psql_available()` pre-flights it. Dropped the now-redundant `schema.extensions.ensure_extensions()` since `Extensions.sql` does the same `CREATE EXTENSION IF NOT EXISTS` calls itself.
- `CreateTables.sql` failed at line 434 with `collation "musicbrainz" for encoding "UTF8" does not exist` because the file uses `COLLATE musicbrainz` unqualified, the collation lives in the `musicbrainz` schema, and our psql invocations started with the server-default `search_path` ("$user", public). `schema/psql.py` now sets `PGOPTIONS='-c search_path=musicbrainz,public -c client_min_messages=WARNING'` on every psql call — byte-for-byte what upstream `admin/InitDb.pl` does. The `client_min_messages=WARNING` also suppresses NOTICE chatter like `CreateCollations.sql`'s "using standard form 'und-u-kf-lower-kn'".
- The import phase aborted immediately with `can't change 'autocommit' now: connection in transaction status INTRANS`. `import_archive()` calls `already_imported()` (a `SELECT` probe on the bookkeeping table) right before entering `bulk_session()`, which left the connection in INTRANS. `bulk_session` then unconditionally assigned `conn.autocommit = False`, and psycopg3 refuses that assignment — even when the new value equals the current one — unless the connection is IDLE. `db.bulk_session()` now only flips the attribute when it actually needs to change, matching the psycopg3 contract.
