# Faster import — planning session

**Date:** 2026-04-24

**Session ID:** 35eda2c3-9be9-4bda-a931-27f6ddb98ee2

## Summary

Diagnosed why the MusicBrainz core-module import takes ~27 min end-to-end, replacing a three-hypothesis hand-wave with live evidence from a fully-monitored fresh run. Identified two distinct bottlenecks in two distinct phases (client-side bz2 during COPY; server-side single-threaded DDL under stock Postgres defaults during post-import). Ruled out the third prior hypothesis (Docker bind-mount) via `docker inspect`. Produced a four-change plan — pbzip2 detection in `open_archive`, `PGOPTIONS` extension, per-file timing log, README guidance for server-start-only knobs. Plan approved.

## Detailed conversation

### User

> When executing the import process, some files take quite long to import. In a previous analysis this was suggested:
>
> Bottleneck. Low server CPU with low throughput usually means one of three things, in decreasing likelihood for this workload:
>
>   1. Client-side bz2 decompression during COPY — tarfile.open(mode="r|bz2") runs in-process and bz2 in CPython is single-threaded. Easy to confirm: top -pid $(pgrep -f musicbrainz-database-setup) during an import; if it's pinned ~100% on one core, that's the bottleneck. Fixes: pipe through pbzip2 -dc or lbzip2 (parallel bz2), or decompress once to disk as .tar and re-open — breaks the "no disk extraction" promise but on a Mac laptop is typically 3–5× faster.
>   2. Single-threaded index builds in the post-phase — PG defaults max_parallel_maintenance_workers=2; bumping to 4–8 (session-scoped SET LOCAL) for CreateIndexes.sql can halve that step. We already do bulk_session tuning for COPY; adding one for post-import DDL is a small change.
>   3. Docker Desktop I/O — on macOS the VFS is slow; docker volume is much faster than bind-mounts. If your data volume is bind-mounted into the container, moving to a named volume often doubles COPY throughput.
>
> I've run "top $(pgrep -f musicbrainz-database-setup | xargs -I{} echo -pid {})" and I get [top screenshot showing python3.12 at 2.8% CPU, psql at 0%, 77.91% idle]

### Assistant

Treated the `top` snapshot as disconfirming the bz2 hypothesis (Python only 2.5% CPU). Launched an Explore agent to trace the COPY pipeline, Postgres config, and post-import DDL orchestration. Key findings:

- `importer/archive.py:20` opens `tarfile.open(mode="r|bz2")` — streaming, no disk extraction.
- `importer/copy.py` streams each member in 1 MiB chunks via psycopg3 `cur.copy().write()`.
- `db.bulk_session()` (`db.py:22`) sets `synchronous_commit=off`, `maintenance_work_mem=2GB`, `work_mem=256MB`, `statement_timeout=0` — but **only around the COPY transaction**.
- Post-import DDL orchestrated in `schema/orchestrator.py` by shelling out to `psql` via `schema/psql.py:69` (`run_sql_file`), with `PGOPTIONS` setting only `search_path` and `client_min_messages`.
- `max_parallel_maintenance_workers` and `max_parallel_workers` not mentioned anywhere in the codebase.

### User

> The import is actually ongoing
> So you can use top or ps to investigate now
> The docker image where we are importing is called musicbrainz-postgres
> And the docker command is installed

### Assistant

Probed the running system directly. `ps` showed the Python process at 2.5% CPU (matching the earlier top), but the Postgres container at **100% CPU** with `psql -f CreateConstraints.sql` as a child — meaning the user's `top` sample caught the **DDL tail**, not the COPY phase.

`pg_stat_activity` showed a single backend running `ALTER TABLE l_artist_work ADD CONSTRAINT ... CHECK (controlled_for_whitespace(entity1_credit))`. `docker inspect` confirmed the data directory is already a **named Docker volume**, ruling out hypothesis #3. `pg_settings` showed stock defaults across the board (`shared_buffers=128MB`, `maintenance_work_mem=64MB`, `max_parallel_maintenance_workers=2`, `synchronous_commit=on`).

Drafted an initial plan file at `/Users/rafa/.claude/plans/when-executing-the-import-gleaming-orbit.md` covering: extend `_PGOPTIONS` for DDL tuning, per-phase elapsed-time log, README guidance for container flags. Treated hypothesis #1 (bz2) as refuted based on the single `top` snapshot — which turned out to be wrong.

### User

> Let's do another full import while you monitor so that we gather all the needed evidence

### Assistant

Accepted the course correction — the previous plan was based on a partial observation window. Designed a measurement setup: drop the current container and volume; recreate fresh on `postgres:17-alpine`; start a 15 s-cadence background sampler capturing `docker stats`, `ps`, `pg_stat_activity`, `pg_stat_progress_copy/create_index/vacuum`; launch the import; let it run end-to-end; gather per-phase timings from `applied_phases`.

Asked three coordination questions via AskUserQuestion (kill vs finish current import; sampling mechanism; baseline vs tuned run).

### User

> (answered via AskUserQuestion)
>
> 1. Stop the postgres container with docker stop musicbrainz-postgres, remove it, start fresh with `docker run -d --name musicbrainz-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17-alpine`, then `uv run musicbrainz-database-setup run --db postgresql://postgres:postgres@localhost:5432/postgres --modules core --latest`
> 2. Background sampler to /tmp (Recommended)
> 3. Baseline untuned (Recommended)

### Assistant

Recreated the container, wrote a read-only sampler to `/tmp/mb-sampler.sh` (cycles through `docker stats`, `ps`, `pg_stat_activity`, and all three `pg_stat_progress_*` views every 15 s, appending to `/tmp/mb-monitor.log`), started it in the background, then launched the import in the background. Armed a `Monitor` tool on the import log to stream phase transitions.

**Immediate finding that inverted the earlier diagnosis:** during the COPY of `musicbrainz.artist_credit`, Python pinned at **100% CPU**, Postgres container only at **38%**, and the COPY backend's `wait_event` was **`Client/ClientRead`** — textbook evidence that Postgres is starved by the client. The prior analysis's hypothesis #1 **is** correct for the COPY phase; the earlier `top` snapshot had just caught the DDL tail where Python is legitimately idle.

### Assistant

As phases progressed, captured samples and updated the plan with the two-phase diagnosis:

- **COPY (14 m 01 s, 52% of the run):** Python bz2 decompression is single-threaded and CPU-bound.
- **Post-import DDL (13 m across three files):** Postgres is on stock defaults with no session tuning from `_PGOPTIONS`. `CreateIndexes` uses parallel maintenance workers (observed 2 shadow pids); `CreateFKConstraints` and `CreateConstraints` are single-threaded per `ALTER TABLE ... ADD CHECK/FK` and compete with autovacuum for cores.

After the import finished (26 m 53 s total), stopped the sampler, queried `applied_phases` for authoritative per-phase durations, and rewrote the plan with full evidence tables — CPU distributions, wait-event tallies partitioned by phase, the stock `pg_settings` snapshot.

### User

> I need to step away from the computer. How can I give you permissions to carry out any tasks for this session in regards to monitoring the import and produce the per-phase timing report and update the plan?

### Assistant

Offered three permission paths: `/permissions` allowlist for specific tool patterns (tightest), Shift+Tab into bypass-permissions mode (loosest), or persistent entries in `.claude/settings.local.json`. Declared the planned scope: monitor until import exit, query `applied_phases`, tear down the sampler, rewrite the plan file, **not** call `ExitPlanMode` so the user reviews on return.

### User

(granted `/permissions` allowlist: `Bash(docker *)`, `Bash(ps *)`, `Bash(grep *)`, `Bash(tail *)`, `Bash(head *)`, `Bash(awk *)`, `Bash(sleep *)`, `Bash(until *)`, `Bash(wait *)`, `Write(/tmp/**)`, `Edit(/Users/rafa/.claude/plans/**)`, then a blanket `Bash` rule.)

### Assistant

Waited for the remaining phase transitions via the running `Monitor` and two `until`-loop background watchers. Captured final per-phase timings:

| Phase | Duration |
|---|---|
| COPY | 14 m 01 s |
| CreateIndexes | 4 m 05 s |
| CreateFKConstraints | 4 m 25 s |
| CreateConstraints | 4 m 22 s |
| **Total** | **26 m 53 s** |

Stopped the sampler, rewrote the plan at `/Users/rafa/.claude/plans/when-executing-the-import-gleaming-orbit.md` with the final evidence, left a status summary for the user's return.

### User

> I've reviewed the plan. Go ahead with the implementation. Just make sure we also add the new `pbzip2` requirement in the README in the Requirements section briefly and in details in the "Requirements in detail" section.

### Assistant

Acknowledged the additional README scope. Exited plan mode, ready to implement the four landing changes plus the requested README structure.

## Evidence artefacts

- `/tmp/mb-baseline.log` — pre-run `pg_settings` + `docker inspect` snapshot.
- `/tmp/mb-monitor.log` — 15 s sampler output across the full run (979 lines).
- `/tmp/mb-import.log` — stdout/stderr of the monitored run.
- `/tmp/mb-sampler.sh` — the sampler script.
