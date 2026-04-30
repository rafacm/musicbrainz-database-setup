# Document manual `psql` ALTER SYSTEM tuning as the recommended speedup path

**Date:** 2026-04-30

## Context

[Issue #13](https://github.com/rafacm/musicbrainz-database-setup/issues/13) proposed a `--auto-tune` flag that would have the tool itself `ALTER SYSTEM SET …` before the import, run, and `ALTER SYSTEM RESET …` afterward — preserving the one-shot `uvx --from git+… run --auto-tune` story while sparing users the need to recreate their Postgres container with `-c` flags.

A grill-me design pass on the proposal collapsed the design tree under its own weight:

- The tool would need a privilege preflight (superuser or `pg_alter_system` membership), apply/revert lifecycle wrapped in `try/finally`, revert-failure handling, partial-apply atomicity reasoning, and (for `shared_buffers`) an optional `--postgres-container` add-on with `docker restart` orchestration. Each is justifiable on its own; together they pile new code paths onto a tool whose stated focus is "point at an existing PostgreSQL instance and touch it as little as possible."
- The user's working preference, surfaced during the grill, was: **don't add a flag — the tool's audience already runs their own Postgres, and we want to touch it as little as possible.** If the instance needs a restart (which `shared_buffers` does), pass on it entirely.

The final decision: **drop the `--auto-tune` feature and document the equivalent two `psql` blocks** in `docs/README.md`. Users opt in by running them; revert is their responsibility. Three commands instead of one, but: zero new code, zero new tests, zero new failure modes, and no privilege footgun. The `docs/README.md` "Server-side tuning (optional)" section is the natural home — it already exists and is already linked from the README quick-start callout.

`shared_buffers` drops out of the documented path entirely. It's postmaster-only — it requires a server restart — and we've explicitly ruled out anything that touches the running instance beyond a `pg_reload_conf()`. Power users who control their Postgres startup can still pass `-c shared_buffers=2GB` themselves; we'll mention that as an aside but stop walking through it.

## Plan

Documentation-only change. No source files under `src/` are touched.

### 1. `docs/README.md` — "Server-side tuning (optional)"

Replace the existing `docker run … -c shared_buffers=2GB -c max_wal_size=8GB …` block with two `psql` blocks (apply, revert) bracketing the `run` command. Four settings only — the SIGHUP-reloadable subset:

```sql
ALTER SYSTEM SET max_wal_size = '8GB';
ALTER SYSTEM SET checkpoint_timeout = '30min';
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET random_page_cost = 1.1;
SELECT pg_reload_conf();
```

The mirror-image `ALTER SYSTEM RESET …` block goes after the `run` command.

Per-setting rationale (the existing bullets in this section) is preserved; the wording shifts from "this `-c` flag does X" to "this `ALTER SYSTEM` does X" but the rationale is the same. `shared_buffers=2GB` — and its bullet — is removed from the documented path.

### 2. `docs/README.md` — Memory-sizing callout

The existing ⚠️ "Memory sizing" callout anchors on `shared_buffers=2GB`. Without that knob in the documented path the callout is orphaned — but the underlying memory-sizing risk (per-session `maintenance_work_mem=2GB` × `1 + max_parallel_maintenance_workers` workers can hit ~5 GB peak during CREATE INDEX) is real on its own and worth keeping.

Rewrite the callout to anchor on `maintenance_work_mem` instead, with a one-line nod that power users who control Postgres startup can additionally pass `-c shared_buffers=2GB` for a further win — pointing them at the upstream Postgres config docs rather than walking them through it ourselves.

### 3. `README.md` — Quick start 💡 callout

Currently:

> 💡 **Want a faster import?** Add server-start tuning flags (`shared_buffers`, `max_wal_size`, `checkpoint_timeout`, …) to roughly halve post-import DDL time. See [Server-side tuning](docs/README.md#server-side-tuning-optional) in the reference guide for the tuned `docker run` and per-flag rationale.

Replace with a wording that points at the new psql-block path:

> 💡 **Want a faster import?** Run two short `psql` blocks before and after the import (no Postgres restart required). See [Server-side tuning](docs/README.md#server-side-tuning-optional) in the reference guide for the statements and per-setting rationale.

Link target is unchanged.

### 4. CHANGELOG entry

Under `## 2026-04-30`, a single `### Changed` entry covering the documentation pivot, with links to the plan, feature doc, and both session transcripts.

### 5. Issue #13 disposition

Post a comment on issue #13 summarizing the grill-me conversation and the resulting decision (auto-tune deferred indefinitely; manual psql tuning documented as the alternative). Close the issue.

### Critical files to touch

| File | Change |
|---|---|
| `docs/README.md` | Replace `docker run -c …` block with two `psql` ALTER SYSTEM blocks (apply, revert). Adjust per-setting rationale bullets. Rewrite ⚠️ Memory-sizing callout to anchor on `maintenance_work_mem` instead of `shared_buffers`. |
| `README.md` | Update Quick start 💡 callout wording to point at psql blocks (not server-start `-c` flags). Link target unchanged. |
| `CHANGELOG.md` | New `## 2026-04-30` `### Changed` entry. |
| `docs/plans/2026-04-30-manual-tuning-statements.md` | This file. |
| `docs/features/2026-04-30-manual-tuning-statements.md` | Feature doc. |
| `docs/sessions/2026-04-30-manual-tuning-statements-{planning,implementation}-session.md` | The standard session pair. |

### Out of scope

- Any source under `src/` — no `--auto-tune` flag, no `tuning.py` module, no privilege preflight.
- New tests — nothing under test changes.
- Container restart automation (`docker restart …`) — explicit non-goal; if the user wants `shared_buffers` they own their Postgres lifecycle.
- A `musicbrainz-database-setup tune apply` / `tune revert` subcommand — discussed and rejected in the grill as an unnecessary middle path; the `psql` one-liners are short enough that wrapping them adds cost without value.

## Verification

Documentation-only — nothing executable to test, and CI is unaffected. The verification surface is:

1. **Render check.** Run `mkdocs serve` (or just preview the Markdown locally) and confirm the new `docs/README.md` section reads cleanly: two fenced `psql` blocks bracketing the `run` command, preserved per-setting rationale, rewritten memory-sizing callout, no broken anchors.
2. **README quick-start callout.** The 💡 link in `README.md` continues to resolve to `docs/README.md#server-side-tuning-optional` (anchor unchanged).
3. **End-to-end smoke.** Manually run the documented sequence against a fresh `postgres:17-alpine` container — `psql` apply block → `musicbrainz-database-setup run --modules core --latest` → `psql` revert block — and confirm:
   - Apply: `SHOW max_wal_size;` returns `8GB`.
   - Revert: `SHOW max_wal_size;` returns the default `1GB`.
   - The import itself completes successfully (no behavior change vs. an untuned run beyond the expected speedup).
4. **Issue #13 closed** with a comment that captures the conversation summary and links to the new docs.
