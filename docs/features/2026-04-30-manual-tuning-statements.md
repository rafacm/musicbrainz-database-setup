# Document manual `psql` ALTER SYSTEM tuning as the recommended speedup path

**Date:** 2026-04-30

## Problem

The "Server-side tuning (optional)" section in `docs/README.md` documented a tuned `docker run … -c shared_buffers=2GB -c max_wal_size=8GB …` invocation as the way to roughly halve post-import DDL time. That works for users who are spinning up their Postgres from scratch alongside the import, but it doesn't help the tool's primary audience: users with an existing Postgres they already operate (a committed `docker-compose.yml` shared with other databases, a managed cloud Postgres, a Homebrew install, …). For those users the documented path is "edit your compose file, restart Postgres, run the tool, restart Postgres again to revert" — friction sharp enough that most just leave the tuning off and accept a slow import.

[Issue #13](https://github.com/rafacm/musicbrainz-database-setup/issues/13) proposed a `--auto-tune` CLI flag that would have the tool itself `ALTER SYSTEM SET …` before the import and `ALTER SYSTEM RESET …` afterward. A grill-me design pass walked the design tree (privilege preflight, lifecycle bracketing, revert-failure handling, partial-apply atomicity, `shared_buffers`-restart edge cases) and concluded the lifecycle complexity didn't pencil out for a tool whose stated focus is "touch the user's Postgres as little as possible." The simpler, honest answer was to document the equivalent `psql` blocks and let the user run them — three commands instead of one, but zero new code, zero new tests, zero new failure modes.

## Changes

| Change | File | Effect |
|---|---|---|
| Replace `docker run -c …` block with two `psql` ALTER SYSTEM blocks | `docs/README.md` | The "Server-side tuning (optional)" section now shows an apply block (`ALTER SYSTEM SET …` × 4 + `pg_reload_conf()`), the import command, and a revert block (`ALTER SYSTEM RESET …` × 4 + `pg_reload_conf()`). Four settings: `max_wal_size`, `checkpoint_timeout`, `effective_io_concurrency`, `random_page_cost` — the SIGHUP-reloadable subset that doesn't require a Postgres restart. Per-setting rationale bullets preserved. |
| Drop `shared_buffers` from the documented path | `docs/README.md` | `shared_buffers` is `postmaster`-only — it can't be reloaded — and the whole point of this change is to avoid restarting the user's Postgres. Mentioned only as a 💡 aside for power users who control their Postgres startup themselves. |
| Privilege note | `docs/README.md` | New short paragraph noting that `ALTER SYSTEM` requires `SUPERUSER` (or `pg_alter_system` on PG 16+), that the default `postgres` Docker user qualifies, and that the settings are server-wide for as long as they're applied. |
| Rewrite ⚠️ "Memory sizing" callout | `docs/README.md` | The callout used to anchor on `shared_buffers=2GB`; with that knob out of the documented path it now anchors on the per-session `maintenance_work_mem=2GB` × `1 + max_parallel_maintenance_workers` workers (~5 GB peak during CREATE INDEX) that the tool sets via `PGOPTIONS`. The OOM-kill anecdote from 2026-04-24 is preserved as a "if you've also pinned `shared_buffers=2GB` at server start" warning. |
| Update Quick start 💡 callout | `README.md` | Wording shifts from "Add server-start tuning flags" to "Run two short `psql` blocks before and after the import — no Postgres restart required." Link target unchanged. |
| Issue #13 closed | GitHub | Comment summarizing the grill-me conversation and the resulting decision (auto-tune deferred indefinitely; manual psql tuning documented as the supported path). |

## Verification

Documentation-only — no executable changes, CI unaffected.

1. **Render check** (Markdown preview or `mkdocs serve`): the new `docs/README.md` section renders cleanly — two fenced `psql` blocks bracketing the `run` command, preserved per-setting rationale, rewritten memory-sizing callout, no broken anchors.
2. **README quick-start callout** still resolves to `docs/README.md#server-side-tuning-optional` (anchor unchanged).
3. **End-to-end smoke** against a fresh `postgres:17-alpine`:

   ```bash
   psql "$DB_URL" -c "SHOW max_wal_size;"   # 1GB (default)

   psql "$DB_URL" <<'SQL'
   ALTER SYSTEM SET max_wal_size = '8GB';
   ALTER SYSTEM SET checkpoint_timeout = '30min';
   ALTER SYSTEM SET effective_io_concurrency = 200;
   ALTER SYSTEM SET random_page_cost = 1.1;
   SELECT pg_reload_conf();
   SQL

   psql "$DB_URL" -c "SHOW max_wal_size;"   # 8GB

   uvx --from git+https://github.com/rafacm/musicbrainz-database-setup \
     musicbrainz-database-setup run --db "$DB_URL" --modules core --latest

   psql "$DB_URL" <<'SQL'
   ALTER SYSTEM RESET max_wal_size;
   ALTER SYSTEM RESET checkpoint_timeout;
   ALTER SYSTEM RESET effective_io_concurrency;
   ALTER SYSTEM RESET random_page_cost;
   SELECT pg_reload_conf();
   SQL

   psql "$DB_URL" -c "SHOW max_wal_size;"   # 1GB (back to default)
   ```

## Files modified

- `docs/README.md` — Server-side tuning section rewritten around two `psql` ALTER SYSTEM blocks; ⚠️ Memory-sizing callout re-anchored on `maintenance_work_mem`; new 💡 aside for `shared_buffers` power users; new privilege note.
- `README.md` — Quick start 💡 callout wording updated to point at the psql-block path.
- `CHANGELOG.md` — entry under `## 2026-04-30`.
- `docs/plans/2026-04-30-manual-tuning-statements.md`, `docs/features/2026-04-30-manual-tuning-statements.md`, `docs/sessions/2026-04-30-manual-tuning-statements-{planning,implementation}-session.md` — the standard plan / feature / session quartet.
