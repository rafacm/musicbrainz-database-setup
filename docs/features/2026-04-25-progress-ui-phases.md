# Polish CLI progress UI — phase model + visual surface

**Date:** 2026-04-25

## Problem

The end-to-end `run` transcript flattened five very different stages into one stream of `INFO` lines and a couple of progress bars. A 2026-04-23 successful run produced:

- Per-call `httpx` chatter at INFO (`HTTP Request: GET https://api.github.com/repos/metabrainz/musicbrainz-server/commits/master "HTTP/1.1 200 OK"`) — eight HTTP lines just to fetch the SQL files.
- Per-SQL-file pairs `INFO Running admin/sql/Extensions.sql` + `INFO admin/sql/Extensions.sql finished in 0.1s` — three artefacts per file once the spinner is counted.
- An indeterminate parent progress row `Import mbdump.tar.bz2  0/?  0/? bytes  ?  0:00:51` that rendered like a broken progress bar.
- No phase boundaries: schema-pre DDL, archive extraction + COPY, and schema-post DDL all bled together with no visible transition.

The user couldn't tell at a glance which step of the pipeline was running, and the screen was dominated by noise from `httpx` rather than the actual progress.

## Changes

| Change | File | Effect |
|---|---|---|
| Phase model | `src/musicbrainz_database_setup/ui/phases.py` (new) + `ui/__init__.py` (new) | `RunPhase` (StrEnum: Mirror / Download / Schema (pre) / Import / Schema (post)), `PHASE_ORDER` tuple, and a `phase_section(phase)` context manager. On entry it emits a `Console.rule("Phase N/5 · <label>", style="bold cyan")` to stderr. On clean exit it emits a single `INFO ✓ <label> · <elapsed>` log line. On exception no footer is emitted — the banner already in scrollback identifies the failing phase, and `_handle_errors` owns the error rendering. A `format_elapsed()` helper renders `0.1s` for sub-minute durations and `M:SS` above. |
| CLI wired to phases | `src/musicbrainz_database_setup/cli.py` | `run` wraps the five-phase pipeline in nested `phase_section` calls inside one outer `progress_session` (collapsed from two so the Live table stays alive across the DB connect boundary). `download` emits Mirror + Download. `schema create --phase pre/post/all` emits the relevant Schema phase(s). `import` emits Import. Trailing `typer.echo("All done.")` / `"Import complete."` / `"Done."` / `"Schema phase … complete"` lines were removed — the phase footer says it. |
| httpx noise gated by `-v` | `src/musicbrainz_database_setup/logging.py` | `configure()` now sets the `httpx` and `httpcore` loggers to WARNING at default verbosity and DEBUG only with `-v`. Their per-request INFO chatter no longer leaks into the default transcript; `--log-file` is unchanged (DEBUG, captures everything). |
| Compact per-SQL-file output | `src/musicbrainz_database_setup/schema/orchestrator.py` | Dropped the `INFO Running admin/sql/X.sql` log (the `psql X.sql` spinner already shows that). Rewrote the completion log from `INFO admin/sql/X.sql finished in 0.1s` to `INFO ✓ admin/sql/X.sql (0.1s)` so it visually pairs with the `✓ <phase>` footer. |
| Real archive header + footer | `src/musicbrainz_database_setup/importer/copy.py` | Removed the indeterminate `Import mbdump.tar.bz2  0/?` parent task. Replaced with `INFO Importing <archive>` at the start, per-table COPY bars (unchanged — those work well), and `INFO ✓ Imported <archive> · N tables · M:SS` on success. Per-table bar descriptions lost the leading two-space indent (no parent to indent under). |
| Tests | `tests/unit/test_ui_phases.py` (new), `tests/unit/test_logging.py` (new) | Five `test_ui_phases` cases pin `PHASE_ORDER` membership, `format_elapsed` boundaries, banner-on-entry, footer-on-success, and no-footer-on-exception. Three `test_logging` cases pin httpx silencing at default and quiet, and DEBUG promotion under `-v`. |

## Key parameters

- `RunPhase` enum has exactly five members in a fixed order. New phases (e.g. a future replication-packet step) extend `PHASE_ORDER` and update `total_phases`. The 1-indexed banner index is computed from the enum's position in `PHASE_ORDER`, so callers don't pass it explicitly.
- `format_elapsed` uses 60 s as the breakpoint between `N.Ns` and `M:SS`. Below 60 s the precision is one decimal; above it rounds to whole seconds. Matches the existing log idiom (`%.1fs`) for short durations and avoids the awkward `124.7s` reading for multi-minute DDL files.
- Banner style is `"bold cyan"`. Cyan is unused elsewhere in the CLI's palette (red = error, yellow = interrupt, dim = progress notes), so the phase rules stand out without colliding with status semantics.
- httpx/httpcore both lifted in lockstep — silencing `httpx` alone leaves `httpcore` chatter; promoting both keeps the `-v` symmetry.

## Verification

- `uv run ruff check src tests` — clean.
- `uv run mypy src` — strict, clean (29 source files).
- `uv run pytest` — 40/40 pass (32 prior + 8 new across `test_ui_phases.py` and `test_logging.py`).
- **Default end-to-end run** (`uv run musicbrainz-database-setup run --modules core --latest --workdir /tmp/mb-cache --yes`):
  - Five `Phase N/5 · …` rules render in order, each in bold cyan.
  - No `HTTP Request: GET …` lines anywhere.
  - No `INFO Running admin/sql/…` lines.
  - One `INFO ✓ admin/sql/X.sql (N.Ns)` line per file in phases 3 and 5.
  - Phase 4 shows only per-table COPY bars (no `Import mbdump.tar.bz2 0/?` row), bracketed by `INFO Importing mbdump.tar.bz2` and `INFO ✓ Imported mbdump.tar.bz2 · N tables · M:SS`.
  - Each phase footer prints once: `INFO ✓ Mirror · 0.4s`, `INFO ✓ Download · 0.0s` (cached), `INFO ✓ Schema (pre) · 1.7s`, `INFO ✓ Import · 14:32`, `INFO ✓ Schema (post) · 7:01`.
- **Verbose run** (`-v`): full httpx chatter returns; phase banners + footers are unchanged.
- **Idempotency re-run** (run a second time against the same DB): banners + footers still print; `_run_file` skips already-applied phases, so phases 3 and 5 finish in <1 s; the `Archive … already imported — skipping.` log appears in phase 4.

## Files modified

- `src/musicbrainz_database_setup/ui/__init__.py` — new, empty package marker.
- `src/musicbrainz_database_setup/ui/phases.py` — new, `RunPhase` enum + `PHASE_ORDER` + `format_elapsed` + `phase_section` context manager.
- `src/musicbrainz_database_setup/logging.py` — promotes `httpx` + `httpcore` to DEBUG only under `-v`.
- `src/musicbrainz_database_setup/cli.py` — wraps `run` / `download` / `schema_create` / `import_` in `phase_section`; collapses `run`'s two `progress_session()` blocks; removes redundant trailing `typer.echo` lines.
- `src/musicbrainz_database_setup/schema/orchestrator.py` — drops `"Running %s"` log; rewrites the completion log to `"✓ %s (%.1fs)"`.
- `src/musicbrainz_database_setup/importer/copy.py` — removes the indeterminate parent task; adds the `Importing` header and `✓ Imported … · N tables · M:SS` footer; un-indents per-table COPY descriptions.
- `tests/unit/test_ui_phases.py` — new, five tests for the phase helper.
- `tests/unit/test_logging.py` — new, three tests for httpx silencing at each verbosity level.
- `CHANGELOG.md` — `### Changed` bullet under `## 2026-04-25` linking the plan, this feature doc, and both session transcripts.
- `README.md` — short note in the "Supported commands" section about the new phase headers and the `-v`-gated httpx output.
- `docs/plans/2026-04-25-progress-ui-phases.md` — plan.
- `docs/sessions/2026-04-25-progress-ui-phases-planning-session.md` — planning transcript.
- `docs/sessions/2026-04-25-progress-ui-phases-implementation-session.md` — implementation transcript.
