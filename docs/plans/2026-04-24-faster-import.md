# Speed up the slow phases of the MusicBrainz import

**Date:** 2026-04-24

## Context

The user asked why some files in the import process take so long, and shared a prior analysis naming three possible bottlenecks. To answer properly, we ran a **fully monitored fresh import** (dropped volume, new `musicbrainz-postgres` on stock `postgres:17-alpine`, 15 s sampler capturing `docker stats` / `ps` / `pg_stat_activity` / `pg_stat_progress_*` throughout). Total run: **26 m 53 s** on the core module.

The headline finding: there are **two distinct bottlenecks in two distinct phases**, and they need different fixes. The prior analysis had one right and one wrong for reasons specific to when each was observed.

### Authoritative per-phase timings (from `applied_phases`)

| Phase | Duration | Notes |
|---|---|---|
| `Extensions.sql` | <0.1 s | |
| `CreateCollations.sql` / `CreateSearchConfiguration.sql` / `CreateTypes.sql` | each <0.1 s | |
| `CreateTables.sql` | 0.29 s | |
| **COPY** (implicit, between end of pre-DDL and start of CreatePrimaryKeys) | **14 m 01 s** | dominant single cost |
| `CreatePrimaryKeys.sql` / `CreateFunctions.sql` | <0.2 s each | |
| **`CreateIndexes.sql`** | **4 m 05 s** | |
| **`CreateFKConstraints.sql`** | **4 m 25 s** | |
| **`CreateConstraints.sql`** | **4 m 22 s** | |
| `SetSequences.sql` / `CreateViews.sql` / `CreateTriggers.sql` | <0.3 s each | |

COPY is ~52 % of the run; the three slow DDL files together are ~48 %.

### Phase 1 — COPY (client-side bz2 decompression is the ceiling)

CPU distribution across the whole run for the Python client (pid 6363): **p50 = 0.8 %, p75 = 99.5 %, max = 100.3 %** — textbook bimodal. During COPY it's pinned; during DDL it's idle waiting on `psql`.

Postgres backend 217 (the COPY target) wait-event tally partitioned to the COPY window:

| wait_event | count | meaning |
|---|---|---|
| `Client/ClientRead` | 33 | backend waiting for client socket |
| `-/-` (actively running) | 18 | |
| `Timeout/VacuumDelay` | 4 | autovacuum noise |
| `IO/DataFileRead` / `IO/DataFileWrite` | 4 | negligible |

`Client/ClientRead` dominating means **Postgres is starved of data because CPython's single-threaded `bz2` decompressor can't deliver it fast enough**. `importer/archive.py` opens `tarfile.open(mode="r|bz2")`; bz2 decompression runs in-process, doesn't release the GIL, and tops out around 35 MB/s of compressed input on this hardware.

**The prior analysis's hypothesis #1 was right** — it was initially mis-refuted because the first `top` sample was taken during the DDL phase, where Python is legitimately idle and the bottleneck sits elsewhere.

### Phase 2 — post-import DDL (server-side, mostly single-threaded, competing with autovacuum)

Wait-event tallies partitioned by DDL file:

| phase | wait_event | count |
|---|---|---|
| `CreateIndexes` | `Timeout/VacuumDelay` | 24 |
| | `-/-` (active) | 23 |
| | `LWLock/WALWrite` / `IO/WalSync` / `IO/BuffileRead` | 3 / 1 / 2 |
| `CreateFKConstraints` | `Timeout/VacuumDelay` | 29 |
| | `-/-` | 11 |
| | `IO/DataFileRead` | 5 |
| `CreateConstraints` | `-/-` | 15 |
| | `Timeout/VacuumDelay` | 11 |
| | `IO/DataFileRead` / `Lock/relation` | 1 / 1 |

Three things stand out:

- **Autovacuum eats measurable CPU.** After COPY, every big table is dirty; autovacuum fires immediately and runs 3 concurrent workers during DDL. `Timeout/VacuumDelay` (68 total samples) means it's throttling itself — but it's still taking cores away from the DDL backend.
- **WAL waits are real but small** (`LWLock/WALWrite`, `IO/WalSync`). `synchronous_commit=on` plus the stock `max_wal_size=1 GB` force frequent fsyncs and checkpoints. Cheap to fix via session/server config.
- **CHECK / FK validation is inherently single-threaded.** No parallel-worker variant exists for `ALTER TABLE ... ADD CONSTRAINT CHECK (...)` or `ADD FOREIGN KEY ... NOT VALID / VALIDATE`. The lever there is *buffer cache + WAL config*, not parallelism.

Container CPU distribution (whole run): p50 = 65.9 %, p75 = 101 %, **max = 202 %**. The 202 % comes from CreateIndexes: `max_parallel_maintenance_workers=2` *is* working — the sampler captured shadow pids (2474, 2528, 2651) alongside the coordinator pid 2457 building btree indexes in parallel. So we're already getting some parallelism there; raising the cap and feeding the workers more memory is the direct lever.

`pg_settings` on the fresh container (all stock):

| setting | value | role |
|---|---|---|
| `shared_buffers` | 128 MB | absurd on a 92 GB-RAM host |
| `maintenance_work_mem` | 64 MB | dominant CREATE INDEX knob |
| `work_mem` | 4 MB | |
| `max_parallel_maintenance_workers` | 2 | used only for btree CREATE INDEX |
| `synchronous_commit` | on | |
| `max_wal_size` | 1 GB | triggers checkpoint storms under bulk load |

`bulk_session()` (`db.py:22`) sets sensible per-session knobs *only* around the COPY transaction. Post-import DDL shells out to `psql` from `schema/psql.py:69`, and `PGOPTIONS` at `schema/psql.py:44` sets *only* `search_path` and `client_min_messages` — **zero tuning reaches the DDL backends.**

### Verdict on the prior analysis

| hypothesis | verdict |
|---|---|
| #1 client-side bz2 decompression | ✅ correct for the COPY phase — fix with `pbzip2`/`lbzip2` |
| #2 single-threaded index builds in post-phase | ✅ correct but wider: also CHECK/FK and WAL/autovacuum contention — fix with `PGOPTIONS` + server-start flags |
| #3 Docker bind-mount I/O | ❌ moot — data directory is already a named volume (`docker inspect` type=`volume`) |

## Plan

Four changes, in order of impact on total runtime.

### 1. Shell out to `pbzip2` (or `lbzip2`) for parallel bz2 decompression

**File:** `src/musicbrainz_database_setup/importer/archive.py` (`open_archive`).

Change `open_archive` to a `@contextmanager` that detects `pbzip2`/`lbzip2` on `PATH` at runtime and, if present, pipes through it, feeding the uncompressed tar stream into `tarfile.open(mode="r|")`. Fall back to stdlib if neither tool is installed.

**Why not decompress to disk:** preserves the "no disk extraction" invariant (upstream MBImport.pl also streams).

**Why detect at runtime:** no hard dependency added. README gains one line: `brew install pbzip2` on macOS, `apt install pbzip2` on Debian/Ubuntu. Absence falls back transparently.

**Expected win:** bz2 is embarrassingly parallel. With 8 threads on this machine, decompression stops being the bottleneck until Postgres itself becomes the limit. Realistic target: **14 m → 3–5 m** on COPY.

### 2. Extend `PGOPTIONS` in `schema/psql.py` with DDL session tuning

**File:** `src/musicbrainz_database_setup/schema/psql.py` (`_PGOPTIONS`).

Append the same knobs `bulk_session()` sets, plus `max_parallel_maintenance_workers`: `synchronous_commit=off`, `maintenance_work_mem=2GB`, `work_mem=256MB`, `max_parallel_maintenance_workers=4`, `statement_timeout=0`.

`PGOPTIONS` passes `-c name=value` pairs as startup options — equivalent to a `SET LOCAL` at session start. Every psql invocation (every DDL file) inherits them automatically.

**Do not touch `bulk_session()`.** It still owns the COPY transaction (a psycopg3 path, distinct from psql subprocess invocations).

**Expected win:** `CreateIndexes.sql` 4 m 05 s → ~2 m. `CreateFKConstraints.sql` and `CreateConstraints.sql` benefit mainly from `synchronous_commit=off` + `work_mem` → call it 4 m → ~3 m each. Combined DDL: ~13 m → ~8 m.

### 3. Per-file elapsed-time log in `schema/orchestrator.py`

**File:** `src/musicbrainz_database_setup/schema/orchestrator.py` (`_run_file`).

Wrap the `run_sql_file` call with `time.monotonic()` and emit `log.info("%s finished in %.1fs", sqlfile.repo_path, elapsed)` on success. Cheap visibility — lets the user see per-file cost without consulting `applied_phases`.

### 4. README — document tuned `docker run`

**File:** `README.md` (Requirements + Requirements in detail).

`shared_buffers`, `max_wal_size`, `checkpoint_timeout`, and `effective_io_concurrency` **must** be set at server start — no `PGOPTIONS` can change them. Add a tuned example in "Requirements in detail" alongside the brief pbzip2 bullet in Requirements.

Keep as guidance, not required — this tool stays backend-agnostic per `AGENTS.md`.

### Critical files to touch

| File | Change |
|---|---|
| `src/musicbrainz_database_setup/importer/archive.py` | Rewrite `open_archive()` as a `@contextmanager` that optionally pipes through `pbzip2`/`lbzip2`. |
| `src/musicbrainz_database_setup/schema/psql.py` | Extend `_PGOPTIONS`. |
| `src/musicbrainz_database_setup/schema/orchestrator.py` | Add timing log around `run_sql_file`. |
| `README.md` | Brief pbzip2 requirement + detailed paragraph + tuned `docker run` example. |
| *(unchanged)* `src/musicbrainz_database_setup/db.py` | `bulk_session()` keeps owning the COPY path. |
| *(unchanged)* `src/musicbrainz_database_setup/importer/copy.py` | `with open_archive(...)` caller is compatible with the preserved signature. |

### Out of scope

- Changing the transaction boundary of the COPY archive — one txn per archive mirrors MBImport.pl.
- Full-extract-to-disk decompression — the pbzip2 pipe is the disk-free alternative and wins anyway.
- Starting/tuning the Postgres container from the tool itself — explicit non-goal per `AGENTS.md`.
- Tuning autovacuum — the `Timeout/VacuumDelay` waits are expected post-bulk and largely self-limiting.

## Verification

1. **Baseline captured** in this run:
   - COPY: 14 m 01 s
   - CreateIndexes: 4 m 05 s
   - CreateFKConstraints: 4 m 25 s
   - CreateConstraints: 4 m 22 s
   - **Total: 26 m 53 s**
2. **After implementing all four items:**
   - `brew install pbzip2` on dev machine.
   - Drop volume, recreate postgres container with the tuned flags.
   - Re-run `musicbrainz-database-setup run --modules core --latest`.
   - Capture new per-file timings from the new log line and from `applied_phases`.
   - **Targets:** COPY ~3–5 m, post-import DDL ~8 m, total **≤ 13 m** (vs 27 m baseline).
3. **Confirm session settings reach psql backends:** during DDL, `SELECT name, setting, source FROM pg_settings WHERE name IN ('maintenance_work_mem','max_parallel_maintenance_workers','synchronous_commit') AND source='client';` should show all three rows.
4. **Confirm pbzip2 is actually in use during COPY:** `ps -ef | grep pbzip2` should show a subprocess; Python `%CPU` should *drop* well below 100 %.
5. **Unit / type checks:** `uv run ruff check`, `uv run mypy`, `uv run pytest`.
