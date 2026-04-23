# Initial implementation

**Date:** 2026-04-22

## Problem

The project was a bare git init with no code. Users wanting a MusicBrainz mirror have to piece together the download, schema, and import steps themselves from the MetaBrainz wiki, `musicbrainz-server/admin/` Perl scripts, and ad-hoc tools like `mbslave` or `musicbrainz-docker`. This feature bootstraps a single Python CLI that consolidates the full pipeline for any existing PostgreSQL 16+ instance.

## Changes

Bootstrapped the repository with a `uv`-managed Python 3.12 package (`src/musicbrainz_database_setup/`) plus Typer CLI (`musicbrainz-database-setup`). The pipeline is split into four subpackages that `cli.run` orchestrates in order:

| Subpackage | Responsibility |
|---|---|
| `mirror/` | List dated dumps, resolve `LATEST`, parse `SHA256SUMS`, resumable range-request download with `.part`-file + rename-on-verify. |
| `sql/` | Resolve a git ref → SHA via GitHub API, fetch `admin/sql/*.sql` via `raw.githubusercontent.com`, cache on disk keyed by SHA, per-module file manifest. |
| `schema/` | Ordered DDL runner matching `admin/InitDb.pl` (Extensions, Collations, Types, Tables → COPY → PrimaryKeys, Functions, Indexes, FKs, Constraints, Sequences, Views, Triggers). Pre-flights `pg_available_extensions`. Records applied phases in `musicbrainz_database_setup.applied_phases`. |
| `importer/` | `tarfile.open(mode="r\|bz2")` streaming; each `mbdump/<table>` member piped into `COPY <schema>.<table> FROM STDIN` via psycopg3's `cursor.copy()`. One transaction per archive. Bookkeeping in `musicbrainz_database_setup.imported_archives`. |

Shared infrastructure: `config.py` (pydantic-settings with `MUSICBRAINZ_DATABASE_SETUP_*` env vars), `errors.py` (typed exceptions with `exit_code` attribute), `logging.py` (rich + file handler), `progress.py` (single `ProgressManager` for nested download/COPY bars), `db.py` (psycopg3 connect + `bulk_session` context manager that SET LOCALs `synchronous_commit=off`, `maintenance_work_mem=2GB`, etc. during COPY).

Docs: `AGENTS.md` with architecture + workflow rules (branching, docs, PR, gh). `CLAUDE.md` is a 2-line pointer to `AGENTS.md`. `docs/README.md` shows how to run against a vanilla `postgres:*` image (including a `docker-compose.yml` snippet).

Tests: 20 unit tests covering manifest ordering, SHA256 parsing, tar member routing, mirror HTML parsing, table→schema mapping.

**Note (2026-04-23):** The plan originally called for a custom Dockerfile layering `musicbrainz_collate` / `musicbrainz_unaccent` C extensions on top of `postgres:16`. Inspection of current upstream (`metabrainz/musicbrainz-server` on master) revealed that the `postgresql-extensions/` directory has been removed, `CreateCollations.sql` is pure ICU (`CREATE COLLATION ... provider = icu`), and `musicbrainz_unaccent` is now a SQL function in `Extensions.sql` — so the custom Dockerfile isn't needed and was deleted. See the `2026-04-23` section of `CHANGELOG.md`.

## Key parameters

| Constant | Value | Why |
|---|---|---|
| `_CHUNK` in `mirror/download.py` and `importer/copy.py` | 1 MiB (`1 << 20`) | Balances syscall overhead vs progress-bar update cadence. |
| `maintenance_work_mem` during COPY | `2GB` | Matches the practical RAM budget of a dev workstation; large enough to keep btree bulk loads in memory. Override via PG config if the box is tighter. |
| `work_mem` during COPY | `256MB` | Keeps sort/hash ops in memory while leaving headroom. |
| `synchronous_commit` during COPY | `off` | Massive speedup; safe because a crash just means rerunning the archive import (idempotent via `imported_archives`). |
| Default `--ref` | `master` | Cache is keyed by resolved SHA, so `master` invalidates on the next upstream commit. Pin to `v-NN-schema-change` tags for reproducibility. |
| Default mirror | `https://data.metabrainz.org/pub/musicbrainz/data/fullexport/` | Official HTTPS mirror. |

## Verification

| # | Command | Expected |
|---|---|---|
| 1 | `uv sync --extra dev` | 37 packages installed. |
| 2 | `uv run musicbrainz-database-setup --help` | Prints the 7-subcommand tree. |
| 3 | `uv run pytest -q` | 20 tests pass. |
| 4 | `uv run ruff check src tests` | Clean. |
| 5 | `uv run musicbrainz-database-setup list-dumps --limit 5` | Returns real dated dirs from `data.metabrainz.org`. |

Integration path (manual, after this PR lands):

```bash
docker run --rm -e POSTGRES_PASSWORD=x -p 5432:5432 postgres:17-alpine
uv run musicbrainz-database-setup run \
    --db postgresql://postgres:x@localhost:5432/postgres \
    --modules core --latest
```

## Files modified

| File | Summary |
|---|---|
| `pyproject.toml` | uv/hatchling project, runtime + dev deps, Typer script entrypoint, ruff/mypy/pytest config. |
| `.python-version`, `.gitignore` | Python 3.12, standard Python ignores. |
| `src/musicbrainz_database_setup/__init__.py`, `__main__.py` | Package + `python -m` entry. |
| `src/musicbrainz_database_setup/cli.py` | Typer app: `list-dumps`, `download`, `schema create`, `import`, `run`, `verify`, `clean`. |
| `src/musicbrainz_database_setup/config.py` | `Settings` class (pydantic-settings) with `MUSICBRAINZ_DATABASE_SETUP_*` env vars. |
| `src/musicbrainz_database_setup/errors.py` | `MBSetupError` hierarchy + `ExitCode` constants. |
| `src/musicbrainz_database_setup/logging.py` | Rich console + optional file handler. |
| `src/musicbrainz_database_setup/progress.py` | `ProgressManager` singleton wrapping `rich.progress.Progress`. |
| `src/musicbrainz_database_setup/db.py` | psycopg3 `connect()` + `bulk_session()` context manager. |
| `src/musicbrainz_database_setup/verify.py` | Read `SCHEMA_SEQUENCE` / `REPLICATION_SEQUENCE` from archives. |
| `src/musicbrainz_database_setup/mirror/{client,index,checksums,download}.py` | httpx wrapper, dated-dir listing, SHA256/MD5 parse + verify, resumable download. |
| `src/musicbrainz_database_setup/sql/{github,cache,manifest}.py` | GitHub ref→SHA resolver, raw fetch, SHA-keyed cache, per-module SQL file lists. |
| `src/musicbrainz_database_setup/schema/{phases,extensions,orchestrator}.py` | Phase enum, `CREATE EXTENSION` preflight, ordered SQL runner with bookkeeping. |
| `src/musicbrainz_database_setup/importer/{archive,tables,copy}.py` | Streaming tar iterator, table→schema routing, `COPY FROM STDIN` loop. |
| `tests/unit/test_{manifest,checksums,index,archive,tables}.py` | 20 offline unit tests. |
| `AGENTS.md` | Architecture + workflow rules (branching, docs, PR, gh). |
| `CLAUDE.md` | Two-line pointer to `AGENTS.md`. |
| `README.md` | Quick-start and config reference. |
| `docs/README.md` | PG 16, contrib, custom collation C extensions, role privileges, disk/network sizing. |
| `docs/plans/2026-04-22-initial-implementation.md` | This feature's plan. |
| `docs/features/2026-04-22-initial-implementation.md` | This document. |
| `docs/sessions/2026-04-22-initial-implementation-{planning,implementation}-session.md` | Session transcripts. |
| `CHANGELOG.md` | Keep-a-Changelog entry for 2026-04-22. |
