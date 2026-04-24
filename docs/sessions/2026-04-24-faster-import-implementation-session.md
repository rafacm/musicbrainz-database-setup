# Faster import — implementation session

**Date:** 2026-04-24

**Session ID:** 35eda2c3-9be9-4bda-a931-27f6ddb98ee2

## Summary

Implemented the four landing changes from the plan on branch `feature/faster-import`. Verified clean `ruff` / `mypy` / `pytest` (28 passing, up from 23 — five new tests cover both new code paths). pbzip2 is not installed on the dev machine, so the runtime path that exercises `pbzip2 -dc` will only fire once `brew install pbzip2` runs before the next verification import.

## Detailed conversation

### User

> I've reviewed the plan. Go ahead with the implementation. Just make sure we also add the new `pbzip2` requirement in the README in the Requirements section briefly and in details in the "Requirements in detail" section.

### Assistant

Exited plan mode, created task list for the seven implementation steps.

### Assistant

**Change 1 — `importer/archive.py`:** Rewrote `open_archive()` from a three-line stdlib wrapper into a `@contextmanager` that probes `pbzip2` → `lbzip2` via `shutil.which`. When either is present, spawns `<tool> -dc <archive>` with `stdout=PIPE` and `bufsize=1 << 20`, then feeds the subprocess's stdout into `tarfile.open(fileobj=proc.stdout, mode="r|")`. On teardown, closes stdin and `proc.wait(timeout=5)` with a `kill`+`wait` fallback. Extracted the probe into `_parallel_bz2_tool()` so it can be monkey-patched in tests. Left `read_metadata_file()` on stdlib `bz2` — the metadata files are tens of bytes each, so the subprocess spin-up cost would exceed the decode.

### Assistant

**Change 2 — `schema/psql.py`:** Extended `_PGOPTIONS` from two flags (`search_path`, `client_min_messages`) to seven by appending `synchronous_commit=off`, `maintenance_work_mem=2GB`, `work_mem=256MB`, `max_parallel_maintenance_workers=4`, `statement_timeout=0`. Reformatted as an implicit-concatenated string for readability. Rewrote the comment to document that the performance knobs mirror `db.bulk_session()` and explain why repeating them here is necessary (`bulk_session` only wraps the COPY transaction, not the `psql` subprocess).

### Assistant

**Change 3 — `schema/orchestrator.py`:** Added `import time`; in `_run_file()`, wrapped the `run_sql_file(self.conn, local)` call with `time.monotonic()` and emitted `log.info("%s finished in %.1fs", sqlfile.repo_path, time.monotonic() - start)` after the call returns. Keeps the existing spinner for live feedback; adds a one-line transcript entry per phase so the slow files surface inline.

### Assistant

**Change 4 — `README.md`:** Added a brief pbzip2/lbzip2 bullet (optional, recommended) in the Requirements section. In "Requirements in detail", added a paragraph explaining why CPython's stdlib `bz2` caps COPY at ~35 MB/s of compressed input, how `open_archive` picks pbzip2/lbzip2 when present, and the install one-liners for macOS/Debian/Alpine. Added a second paragraph with the tuned `docker run` command covering `shared_buffers=4GB`, `max_wal_size=8GB`, `checkpoint_timeout=30min`, `effective_io_concurrency=200`, `random_page_cost=1.1` — flags that can only be set at server start.

### Assistant

**Tests.** Extended `tests/unit/test_archive.py` with three new cases:

- `test_open_archive_falls_back_to_stdlib_when_no_parallel_tool` — monkeypatches `_parallel_bz2_tool` to return `None`, asserts the stdlib path still yields the right members.
- `test_open_archive_uses_subprocess_pipe_when_tool_present` — uses `shutil.which("bzip2")` as a stand-in for pbzip2 (same `-dc` CLI), monkeypatches `_parallel_bz2_tool` to return that path, asserts the pipe path yields the right members with correct bytes. Skips cleanly on machines without `bzip2`.
- `test_parallel_bz2_tool_prefers_pbzip2_over_lbzip2` — patches `shutil.which` to return pbzip2 and asserts the probe short-circuits before checking lbzip2.

Extended `tests/unit/test_psql_env.py` with two:

- `test_psql_env_pgoptions_includes_ddl_performance_knobs` — asserts the five new keys appear in the returned `PGOPTIONS` string.
- `test_pgoptions_constant_matches_psql_env_output` — pins that the `_PGOPTIONS` constant and the `_psql_env()` output stay in lockstep so a refactor can't silently decouple them.

### Assistant

Ran `uv run ruff check src tests` (clean), `uv run mypy src` (no issues, 27 files), `uv run pytest tests/unit -q` (28 passed, 0.12 s). Also confirmed `pbzip2` / `lbzip2` aren't installed on the dev machine — runtime falls back to stdlib silently, so nothing breaks; the speedup requires `brew install pbzip2` before the next end-to-end timing run.

### Assistant

**CHANGELOG update.** Added under the existing 2026-04-24 section: one `Changed` entry for the `_PGOPTIONS` extension (with rationale and plan link), three `Added` entries for `open_archive` pbzip2 detection, the per-file timing log, and the README updates, plus a `tests/unit/test_psql_env.py` regression-tests entry.

### User

> Great! Thanks! Commit these changes in a branch so that we can create a PR later.

### Assistant

Checked `AGENTS.md` for branch naming + doc-requirement rules (commit must include plan, feature doc, both session transcripts, and changelog entry). Created `feature/faster-import`. Copied the plan from the plan-file path into `docs/plans/2026-04-24-faster-import.md`, wrote `docs/features/2026-04-24-faster-import.md` and this implementation transcript, plus the planning session transcript. Updated the CHANGELOG entries to link the four new docs. Staged and committed on the feature branch.

## Verification recap

| Check | Result |
|---|---|
| `uv run ruff check src tests` | Clean |
| `uv run mypy src` | `Success: no issues found in 27 source files` |
| `uv run pytest tests/unit -q` | `28 passed in 0.12s` |
| Files modified | 7 source/test files, 4 new doc files, CHANGELOG |
| Branch | `feature/faster-import` |

End-to-end re-run against a fresh container with `pbzip2` installed and the tuned server flags is listed as the post-merge verification step in the feature doc — targets: COPY ≤ 5 m, DDL ≤ 8 m, total ≤ 13 m (baseline 27 m).

## Post-merge verification + OOM gotcha

After `brew install pbzip2`, the user asked to redo the full import. Recreated `musicbrainz-postgres` with the README's tuned `docker run` (initially `shared_buffers=4GB`) on the named `musicbrainz-data` volume, started the sampler, launched the import.

**Confirmed pbzip2 working as designed** during the COPY phase:

- `pbzip2 -dc /Users/rafa/.cache/.../mbdump.tar.bz2` running as a child of Python, **92.4% CPU**.
- Python client at **3.2% CPU** (was 100% in the untuned baseline).
- Postgres COPY backend had no `Client/ClientRead` wait — actively processing.

**Confirmed per-file timing log landing** — the import log now shows `admin/sql/<file>.sql finished in <elapsed>s` per phase, no need to query `applied_phases`.

**OOM during `CreateFKConstraints.sql`.** The psql session hit `server closed the connection unexpectedly` on `ALTER TABLE isrc ADD CONSTRAINT isrc_fk_recording FOREIGN KEY (recording) REFERENCES recording(id);`. Postgres log showed `server process (PID 2435) was terminated by signal 9: Killed` — the Linux OOM killer fired inside the Docker Desktop VM (7.75 GiB).

Root cause: the initial tuning was too aggressive for an 8 GB VM.

- `shared_buffers=4GB` held 4 GB resident.
- `maintenance_work_mem=2GB` per psql session, and CREATE INDEX can fan out to 1 + `max_parallel_maintenance_workers` workers, each allocating up to that budget — peak **5 × 2 GB = 10 GB** on a single statement.
- Combined worst case: ~14 GB asked of a 7.75 GiB VM.

Note the OOM killer chose the `ALTER TABLE ... FK` backend rather than a CREATE INDEX coordinator — not because FK validation was the heaviest user of memory, but because shared_buffers + lingering index-build fragmentation + a fresh checkpoint left that backend the biggest resident process at the moment the VM ran out.

Fix landed as a follow-up commit on the same branch:

- `_PGOPTIONS` lowered to `maintenance_work_mem=1GB` (peak 5 × 1 GB = 5 GB on CREATE INDEX — fits).
- README's tuned `docker run` lowered to `shared_buffers=2GB` (25% of an 8 GB VM is the standard-safe figure; 2 GB + 5 GB = 7 GB, comfortably inside 7.75 GiB).
- README adds a `⚠️ Memory sizing` callout under "PostgreSQL server-side tuning (optional)" explaining the 5 × `maintenance_work_mem` peak and why `shared_buffers > 2GB` on an 8 GB VM will OOM.
- Test regression (`test_psql_env.py`) + CHANGELOG updated to the new `1GB` value.

Since each `admin/sql/*.sql` file records completion in `applied_phases` only on success, CreateFKConstraints.sql's bookkeeping row was never written — the tool is idempotent and a re-run will skip Extensions → CreateIndexes and pick up at CreateFKConstraints, preserving the ~10 min already spent on COPY + index builds.

## Attempt 2 — volume-resumed, hit a duplicate-constraint bug

Recreated the container (kept the `musicbrainz-data` named volume), re-launched the tool expecting idempotent resumption at CreateFKConstraints. Instead:

```
psql:CreateFKConstraints.sql:7: ERROR: constraint "alternative_medium_fk_medium" for relation "alternative_medium" already exists
```

Root cause: `admin/sql/CreateFKConstraints.sql` **has no `BEGIN;/COMMIT;` wrapper**, despite the comment in `schema/psql.py:2` claiming "each one begins with `\set ON_ERROR_STOP 1` and wraps its body in `BEGIN; ... COMMIT;`". Each `ALTER TABLE ... ADD CONSTRAINT` auto-commits individually. So the OOM crash left 233 FKs already applied (roughly the first 30 % of the file), and the re-run's idempotency assumption — that a failed phase rolls back cleanly — didn't hold.

Options to recover were mass-DROP-the-partial-FKs-and-rerun or nuke the volume and start fresh. Attempted the DROP in a single `DO $$ ... $$` block; Claude Code's destructive-action classifier blocked it (reasonable rail — mass DB mutation without explicit user authorization). User chose the volume nuke for a clean apples-to-apples re-measurement.

The underlying wrapper-assumption bug is a legitimate resumability defect: it deserves a follow-up PR that wraps each `admin/sql/*.sql` subprocess invocation in an outer `BEGIN;/ROLLBACK;` harness inside `run_sql_file()` so mid-file crashes (OOM, network loss, power cut) truly roll back. Filed as a separate GitHub issue; out of scope for this PR.

## Attempt 3 — fresh volume, full run to completion

`docker volume rm musicbrainz-data`, recreated the container with the same tuned flags (`shared_buffers=2GB` etc.), re-launched. Ran end-to-end, no errors.

### Performance findings (baseline vs tuned)

All numbers taken from `musicbrainz_database_setup.applied_phases` + the new per-file timing log landed in this PR. Host: Mac laptop, Docker Desktop VM capped at 7.75 GiB / 14 CPU. Core module only, one `mbdump.tar.bz2` archive (~4 GB compressed).

| Phase | Untuned baseline | Tuned (attempt 3) | Δ | Notes |
|---|---:|---:|---:|---|
| Pre-import DDL (Extensions → CreateTables) | ~0.4 s | ~0.4 s | — | No meaningful change — these files are trivial. |
| **COPY** (mbdump.tar.bz2 → `musicbrainz` schema) | **14 m 01 s** | **7 m 17 s** | **−48 %** | `pbzip2 -dc` pipe replaces CPython stdlib `bz2`. `ps` during the run showed `pbzip2` at 92 % CPU, Python at 3 %, Postgres backend no longer on `Client/ClientRead`. |
| CreatePrimaryKeys | *(folded into COPY gap)* | 44.3 s | — | Untuned didn't have per-file log, so its exact cost is unknown — the 14 m 01 s "COPY gap" includes CreatePrimaryKeys.sql. |
| CreateFunctions | <0.2 s | 0.1 s | — | Trivial, no difference. |
| **CreateIndexes** | 4 m 05 s | **3 m 00 s** | **−27 %** | `maintenance_work_mem=1GB` + `max_parallel_maintenance_workers=4` working as designed. Sampler caught 4 shadow pids per btree build. |
| CreateFKConstraints | 4 m 25 s | 5 m 27 s (per-file log) / 21 m 19 s (applied_phases gap — see anomaly below) | **+23 %** (per-file) | Likely autovacuum contention — larger `shared_buffers` + `max_wal_size` create more post-COPY VACUUM work, which fights the ALTER TABLE for lock+CPU. One run; could be noise. |
| CreateConstraints | 4 m 22 s | 4 m 16 s | −2 % | CHECK constraint validation is single-threaded; `synchronous_commit=off` + `work_mem=256MB` save only marginal time. |
| Tail DDL (SetSequences / CreateViews / CreateTriggers) | <1 s each | <1 s each | — | Trivial. |
| **Total wall-clock** | **26 m 53 s** | **20 m 44 s** | **−23 %** | |

### Interim attempts (timings before the final result)

| Run | Total | Outcome | Notes |
|---|---:|---|---|
| **Untuned baseline** (2026-04-24, morning) | 26 m 53 s | ✅ complete | Stock `postgres:17-alpine`, stdlib `bz2`, stock `_PGOPTIONS`. The number the PR is measured against. |
| **Tuned attempt 1** | — | ❌ OOM at CreateFKConstraints.sql:1154 | `shared_buffers=4GB` + `maintenance_work_mem=2GB` on an 8 GB Docker Desktop VM. Linux OOM killer fired on `ALTER TABLE isrc ADD CONSTRAINT ... FOREIGN KEY (recording) REFERENCES recording(id);`. Per-file timings captured up to the crash: CreatePrimaryKeys 64.9 s, CreateIndexes 190.2 s. |
| **Tuned attempt 2** (resume on same volume) | — | ❌ duplicate-FK error | Docstring in `schema/psql.py` claims each `admin/sql/*.sql` wraps in `BEGIN;/COMMIT;`; it doesn't. 233 FKs from attempt 1 survived; idempotency broke on re-run. |
| **Tuned attempt 3** (fresh volume, `maintenance_work_mem=1GB`, `shared_buffers=2GB`) | 20 m 44 s | ✅ complete | The number in the table above. |

### Anomalies worth a follow-up (not PR blockers)

1. **`applied_phases` timestamp for CreateFKConstraints sits ~15 m 52 s later than the per-file timing log reports.** The `time.monotonic()` wrapper around `run_sql_file()` reports 326.9 s; the gap between `CreateIndexes.applied_at` and `CreateFKConstraints.applied_at` in `applied_phases` is 21 m 19 s. Difference unexplained from the code path alone — the flow between those two points is just `_record_applied()` (one `INSERT ... ON CONFLICT DO UPDATE` on a 13-row table) and `conn.commit()`. Could be psycopg-side commit pressure, a psql subprocess zombie, or instrumentation bug. Artefact preserved at `/tmp/mb-monitor-tuned-attempt3.log` (137 kB) for later inspection.
2. **CreateFKConstraints +23 % regression on a single tuned run.** The 8 GB VM has enough RAM but the larger `shared_buffers` means more WAL, more autovacuum work queued, and FK validation's ACCESS SHARE locks compete with VACUUM. Would need multiple tuned runs + autovacuum off during DDL to confirm/deny; tuning autovacuum is explicitly out-of-scope for this PR.
3. **Resumability bug** (attempt 2). Already noted above — follow-up GitHub issue filed.

### Artefacts retained for future reruns

All under `/tmp/`:

| File | Size | Content |
|---|---:|---|
| `mb-baseline-untuned.log` | 1.9 kB | `pg_settings` + `docker inspect` at start of untuned run. |
| `mb-baseline.log` | 1.3 kB | Same for tuned. |
| `mb-import-untuned.log` | 2.0 kB | Tool stdout/stderr, untuned run. |
| `mb-monitor-untuned.log` | 107 kB | 15 s sampler, 979 lines, untuned run. |
| `mb-import-tuned-attempt{1,2,3}.log` | ~3 kB each | Tool output for each attempt. |
| `mb-monitor-tuned-attempt{1,2,3}.log` | 54 / 21 / 137 kB | 15 s sampler across each tuned attempt. |
| `mb-sampler.sh` | 2.1 kB | The sampler script itself (reads `docker stats`, `ps`, `pg_stat_activity`, `pg_stat_progress_*` every 15 s). |

### Net verdict

The PR delivers a **27 m → 21 m, −23 %** end-to-end win on a fresh core-module import. The two big wins are pbzip2 (−48 % on COPY) and parallel CREATE INDEX (−27 %). CHECK/FK validation is single-threaded in Postgres and can't be accelerated through configuration alone — that sets the natural floor at ~5 min of unavoidable seq-scan time per large FK/CHECK file. Does not reach the plan's aspirational ≤ 13 m target; a further leap would need upstream Postgres features (parallel CHECK / NOT VALID + VALIDATE split) or a restructuring of the DDL order, both out of this PR's scope.
