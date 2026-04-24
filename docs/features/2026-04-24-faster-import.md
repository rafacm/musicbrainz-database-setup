# Faster import

**Date:** 2026-04-24

## Problem

A monitored fresh core-module import against stock `postgres:17-alpine` took **26 m 53 s**. Live instrumentation (15 s sampler of `docker stats`, `ps`, `pg_stat_activity`, `pg_stat_progress_*`) revealed two unrelated bottlenecks in two distinct phases:

- **COPY phase (14 m 01 s):** the Python client sits pinned at 100 % on one core; the Postgres backend waits on `wait_event = Client/ClientRead`. `tarfile.open(mode="r|bz2")` routes decompression through CPython's stdlib `bz2`, which is single-threaded and doesn't release the GIL — this is the ceiling for every table's COPY.
- **Post-import DDL (4 × ~4 min):** `CreateIndexes.sql`, `CreateFKConstraints.sql`, `CreateConstraints.sql` run under stock Postgres defaults (`maintenance_work_mem=64 MB`, `synchronous_commit=on`, `shared_buffers=128 MB`). `db.bulk_session()` only wraps the COPY transaction via psycopg3; the `psql` subprocess that runs the DDL inherits none of those knobs.

Neither Docker Desktop I/O (hypothesis #3 in the user-shared analysis) nor WAL write volume turned out to be meaningful — the data directory is already a named Docker volume, and WAL waits (`LWLock/WALWrite`, `IO/WalSync`) account for just 4 of the 107 DDL-window samples.

## Changes

Four in-tree changes land together:

| Change | File(s) | Effect |
|---|---|---|
| **pbzip2/lbzip2 detection in `open_archive()`** | `importer/archive.py` | When either tool is on `$PATH`, `open_archive` spawns `<tool> -dc <archive>` and reads an uncompressed tar stream off stdin. Stdlib `bz2` fallback is preserved, so absence is not fatal. |
| **`_PGOPTIONS` extended with DDL tuning** | `schema/psql.py` | Every `psql` invocation now inherits `synchronous_commit=off`, `maintenance_work_mem=1GB`, `work_mem=256MB`, `max_parallel_maintenance_workers=4`, `statement_timeout=0` — the same knobs `bulk_session()` applies to COPY, now reaching the DDL backends too. |
| **Per-file elapsed-time log** | `schema/orchestrator.py` | `_run_file()` emits `<phase> finished in <elapsed>s` after each `admin/sql/*.sql` file, so slow phases surface inline in the transcript. |
| **README guidance** | `README.md` | New `pbzip2` bullet in Requirements; detailed paragraph in Requirements in detail explaining why stdlib `bz2` is the COPY ceiling; tuned `docker run` with server-start-only flags (`shared_buffers`, `max_wal_size`, `checkpoint_timeout`, `effective_io_concurrency`, `random_page_cost`). |

`db.bulk_session()`, `importer/copy.py`, and the `admin/sql/*.sql` fetch/cache layer are untouched — the COPY transaction boundary and the upstream-InitDb.pl alignment are preserved.

## Key parameters

| Constant | Value | Why |
|---|---|---|
| `pbzip2` / `lbzip2` probe order in `archive._parallel_bz2_tool()` | `pbzip2` → `lbzip2` → stdlib | Both are drop-in `bzip2 -dc` replacements; `pbzip2` is more widely available. |
| `subprocess.Popen.bufsize` in `open_archive` | 1 MiB | Keeps the pipe from blocking on tiny reads; matches `_CHUNK` in `importer/copy.py`. |
| `maintenance_work_mem` via `PGOPTIONS` | 1 GB | Dominant knob for CREATE INDEX. Initially 2 GB to match `bulk_session()`, lowered to 1 GB after a `CreateFKConstraints.sql` OOM on an 8 GB Docker Desktop VM — with `max_parallel_maintenance_workers=4`, CREATE INDEX can allocate 5 × `maintenance_work_mem`, so 1 GB keeps peak at 5 GB and leaves room for `shared_buffers`. |
| `work_mem` via `PGOPTIONS` | 256 MB | Covers sort/hash spills during CHECK/FK validation. |
| `max_parallel_maintenance_workers` via `PGOPTIONS` | 4 | Observed 2 (default) workers firing during index builds with 8-worker server cap; 4 doubles per-index parallelism without overrunning `max_worker_processes=8`. |
| `synchronous_commit` via `PGOPTIONS` | `off` | Removes the `IO/WalSync` fsync-per-commit seen in the DDL wait profile. Crash-safety note: the tool's DDL phases are idempotent via `applied_phases`. |

## Verification

| # | Command | Expected |
|---|---|---|
| 1 | `uv run ruff check src tests` | Clean. |
| 2 | `uv run mypy src` | `Success: no issues found in 27 source files`. |
| 3 | `uv run pytest tests/unit -q` | `28 passed` (was 23 before this feature; 5 new tests cover the two new code paths). |
| 4 | `brew install pbzip2 && which pbzip2` | Prints `/opt/homebrew/bin/pbzip2` (or `/usr/local/bin/pbzip2` on Intel). |
| 5 | Fresh import: drop container + named volume, recreate with the tuned flags from the README, `musicbrainz-database-setup run --modules core --latest`. | New per-file log line shows each phase's elapsed time; COPY ≤ 5 m; post-DDL ≤ 8 m; total ≤ 13 m (baseline: 27 m). |
| 6 | During DDL, `SELECT setting, source FROM pg_settings WHERE name='maintenance_work_mem' AND source='client';` | Returns `1GB`, `client`. |
| 7 | During COPY, `ps -ef \| grep pbzip2` | Shows a subprocess; Python `%CPU` drops well below 100 %. |

## Files modified

| File | Summary |
|---|---|
| `src/musicbrainz_database_setup/importer/archive.py` | `open_archive` is now a `@contextmanager` that optionally pipes through `pbzip2`/`lbzip2`. New `_parallel_bz2_tool()` helper does the `shutil.which` probe. |
| `src/musicbrainz_database_setup/schema/psql.py` | `_PGOPTIONS` extended with five performance knobs; comment explains why they duplicate `bulk_session()`. |
| `src/musicbrainz_database_setup/schema/orchestrator.py` | `import time`; `_run_file()` wraps `run_sql_file` with `time.monotonic()` and logs elapsed. |
| `tests/unit/test_archive.py` | Three new tests: stdlib fallback, subprocess pipe (via `bzip2 -dc` stand-in), `shutil.which` probe order. |
| `tests/unit/test_psql_env.py` | Two new tests: regression on `PGOPTIONS` contents, `_PGOPTIONS` constant matches `_psql_env()` output. |
| `README.md` | Brief pbzip2 bullet in Requirements + detailed paragraph + tuned `docker run` in Requirements in detail. |
| `CHANGELOG.md` | 2026-04-24 entry linking plan, feature doc, and session transcripts. |
| `docs/plans/2026-04-24-faster-import.md` | This feature's plan. |
| `docs/features/2026-04-24-faster-import.md` | This document. |
| `docs/sessions/2026-04-24-faster-import-{planning,implementation}-session.md` | Session transcripts. |
