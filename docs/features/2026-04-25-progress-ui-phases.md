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
| Phase model | `src/musicbrainz_database_setup/ui/phases.py` (new) + `ui/__init__.py` (new) | `RunPhase` (StrEnum with action-oriented labels: Locate dump / Download / Schema setup / Import tables / Schema finalize), `PHASE_ORDER` tuple, and a `phase_section(phase)` context manager. On entry it emits `==> Phase N/5 · <label>` (Homebrew-style prefix in bold blue) to stderr. On clean exit it emits a single `✓ <label> complete · <elapsed>` log line. On exception no footer is emitted — the banner already in scrollback identifies the failing phase, and `_handle_errors` owns the error rendering. `format_elapsed()` renders `0.1s` for sub-minute durations and `M:SS` above; `format_size()` renders byte counts in binary units (KiB / MiB / GiB / TiB). |
| CLI wired to phases | `src/musicbrainz_database_setup/cli.py` | `run` wraps the five-phase pipeline in nested `phase_section` calls inside one outer `progress_session` (collapsed from two so the Live table stays alive across the DB connect boundary). `download` emits Locate dump + Download. `schema create --phase pre/post/all` emits the relevant Schema phase(s). `import` emits Import tables. Locate-dump body logs `Mirror: <url>`, `SQL ref <ref> → <SHA>`, `Selected dump: <name>`, `Local cache: <path>`. Download body logs `Downloading N file(s): <list>` before the loop. Trailing `typer.echo("All done.")` / `"Import complete."` / `"Done."` / `"Schema phase … complete"` lines were removed — the phase footer says it. |
| httpx noise gated by `-v` | `src/musicbrainz_database_setup/logging.py` | `configure()` sets the `httpx` and `httpcore` loggers to WARNING at default verbosity and DEBUG only with `-v`. Their per-request INFO chatter no longer leaks into the default transcript; `--log-file` is unchanged (DEBUG, captures everything). |
| Hide INFO prefix; keep `Warning:` / `Error:` labels | `src/musicbrainz_database_setup/logging.py` | `RichHandler(..., show_level=False, ...)` drops the leading `INFO` column on routine progress lines. A new `_SeverityRichHandler.render_message` override prepends an explicit `Warning: ` / `Error: ` text label (yellow / red bold) only for WARNING and ERROR records — matching the convention used by `cargo`, `npm`, `pip`, `brew`, `gh`, and `terraform`. clig.dev advises against generic level prefixes on routine output but does not address how to mark warnings/errors; the text-label-on-severity pattern is the consistent answer across major user-facing CLIs. The labels survive `--no-color` / `NO_COLOR` / piped stderr, so severity stays readable when colour is stripped. |
| Drop redundant M-of-N column | `src/musicbrainz_database_setup/progress.py` | Removed `MofNCompleteColumn` from the shared `Progress`. For byte-based tasks the `DownloadColumn` already renders progress in human binary units (e.g. `902.8/1226.0 MiB`); the M-of-N column was duplicating the same totals as raw byte counts and crowding the row. |
| No more lingering download row | `src/musicbrainz_database_setup/mirror/download.py` | `download_archive` now removes the live progress task in `finally` (previously the row stayed in the table through every subsequent phase) and emits a `✓ Downloaded <archive> · <size>` log on success so the work is recorded in scrollback. |
| Compact per-SQL-file output | `src/musicbrainz_database_setup/schema/orchestrator.py` | Dropped the `Running admin/sql/X.sql` log (the `psql X.sql` spinner already shows that). Rewrote the completion log to `✓ Applied admin/sql/X.sql · 0.1s` — explicit verb prefix and middle-dot separator that visually pair with the `✓ <phase>` footer. |
| Per-table import logs | `src/musicbrainz_database_setup/importer/copy.py` | Removed the indeterminate `Import mbdump.tar.bz2  0/?` parent task. `import_archive` opens with `Importing tables from <archive>` and closes with `✓ Imported <archive> · N tables · M:SS`. Each `_copy_member` now logs `✓ Table <schema>.<table> · <size>` after the COPY succeeds, so the imported table list is durable in scrollback (previously each table existed only as a transient progress row that vanished on completion). |
| Tests | `tests/unit/test_ui_phases.py` (new), `tests/unit/test_logging.py` (new) | Seven `test_ui_phases` cases pin `PHASE_ORDER` membership, the verbatim phase labels (so a casual rename surfaces in code review), `format_elapsed` boundaries, `format_size` across each unit, banner-on-entry, footer-on-success, and no-footer-on-exception. Three `test_logging` cases pin httpx silencing at default and quiet, and DEBUG promotion under `-v`. |

## Key parameters

- `RunPhase` enum has exactly five members in a fixed order. New phases (e.g. a future replication-packet step) extend `PHASE_ORDER` and update `total_phases`. The 1-indexed banner index is computed from the enum's position in `PHASE_ORDER`, so callers don't pass it explicitly.
- Phase labels are user-facing strings (banners + footers) and pinned by `tests/unit/test_ui_phases.py::test_phase_labels_are_action_oriented` so a casual rename surfaces in code review.
- `format_elapsed` uses 60 s as the breakpoint between `N.Ns` and `M:SS`. Below 60 s the precision is one decimal; above it rounds to whole seconds. Matches the existing log idiom (`%.1fs`) for short durations and avoids the awkward `124.7s` reading for multi-minute DDL files.
- `format_size` uses 1024-based binary units (KiB / MiB / GiB / TiB), saturating at TiB. One decimal place throughout. Matches Rich's `DownloadColumn(binary_units=True)` so the bar and the post-COPY log line use the same vocabulary.
- Banner uses a `==>` prefix in `bold blue` (Homebrew-style). The prefix is rendered via `console.print(...)` with Rich markup; in `--no-color` / non-TTY mode the styling is stripped automatically and the marker remains as plain ASCII `==>`. This replaced an earlier full-width `Console.rule(...)` design that visually broke the log stream into sections and depended on terminal width. Both `brew`, `git` porcelain scripts, and most build tools use the same `==>` marker, so it's a familiar pattern.
- httpx/httpcore both lifted in lockstep — silencing `httpx` alone leaves `httpcore` chatter; promoting both keeps the `-v` symmetry.
- `RichHandler(show_level=False)` hides the generic `INFO` column. Severity for WARNING / ERROR is reintroduced as a text prefix (`Warning:` / `Error:`) via `_SeverityRichHandler.render_message` so it survives `--no-color` and piped stderr — Rich's level styling alone (which the previous revision relied on) is invisible whenever colour is stripped, which makes warnings and errors indistinguishable from progress text in those environments.

## Round-2 refinements (post Evil Martians review)

After the first end-to-end test the work was reviewed against the [Evil Martians CLI progress patterns article](https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays). The review surfaced four concrete gaps which were addressed in the same PR:

1. **X-of-Y count prefix.** Every per-step log line now carries `(N/total)`: `✓ (1/5) Applied admin/sql/Extensions.sql · 0.1s`, `✓ (1/3) Downloaded mbdump.tar.bz2 · 1.2 GiB`, `(1/2) Importing tables from <archive>` + `✓ (1/2) Imported <archive>`. `Orchestrator._run_file`, `download_archive`, and `import_archive` gained `index` / `total` keyword args; the CLI computes them by `enumerate(list(...), start=1)` against the manifest. Per-table COPY lines deliberately stay count-less because streaming `tarfile.open(mode="r|bz2")` cannot enumerate members up-front (acknowledged in `AGENTS.md` "Tricky bits").
2. **Green checkmarks.** A new `_CheckmarkHighlighter` (subclass of `rich.highlighter.Highlighter`) attached to `RichHandler` styles every literal `✓` character bold green, without embedding Rich markup in the log message. The file handler therefore receives plain `✓` text — no `[green]…[/]` leaks into `--log-file`.
3. **Past-tense phase footer.** `phase_section` footer changed from `✓ <label> · <elapsed>` to `✓ <label> complete · <elapsed>` so the line reads grammatically for noun-style labels (`Schema setup`, `Locate dump`) too. Aligns with the article's verb-tense recommendation.
4. **`--no-color` flag.** New global `--no-color` Typer option. `configure()` sets `NO_COLOR=1` *before* the `Console` is constructed and resets the cached singleton via a new `_reset_console()` helper so the env var is honoured. Externally-set `NO_COLOR` continues to work as before (Rich handles it natively at Console init).

A fifth gap — proper progress reporting for the slow `CreateIndexes.sql` / `CreateFKConstraints.sql` files via `pg_stat_progress_*` polling on a side connection — is tracked separately in [issue #8](https://github.com/rafacm/musicbrainz-database-setup/issues/8) for follow-up.

## Verification

- `uv run ruff check src tests` — clean.
- `uv run mypy src` — strict, clean (29 source files).
- `uv run pytest` — 44/44 pass (32 prior + 12 new across `test_ui_phases.py` and `test_logging.py`).
- **Default end-to-end run** (`uv run musicbrainz-database-setup run --modules core --latest --workdir /tmp/mb-cache --yes`):
  - Five `Phase N/5 · …` rules render in order, each in bold cyan: `Locate dump`, `Download`, `Schema setup`, `Import tables`, `Schema finalize`.
  - No `HTTP Request: GET …` lines anywhere.
  - No leading `INFO` column on log lines (cleaner default output); WARNING / ERROR records still stand out by Rich's per-level message colour.
  - Locate dump body shows: `Mirror: https://data.metabrainz.org/.../fullexport`, `SQL ref master → 2082249951e5`, `Selected dump: 20260422-002337`, `Local cache: /tmp/mb-cache/20260422-002337`.
  - Download body shows: `Downloading 1 file(s): mbdump.tar.bz2`, then a single live progress row that disappears on completion, then `✓ Downloaded mbdump.tar.bz2 · 1.2 GiB`.
  - Schema setup / Schema finalize: one `✓ Applied admin/sql/<X>.sql · N.Ns` per file.
  - Import tables: `Importing tables from mbdump.tar.bz2`, then one `✓ Table musicbrainz.<table> · <size>` per COPY (177 lines for core), then `✓ Imported mbdump.tar.bz2 · 177 tables · M:SS`.
  - Each phase footer prints once: `✓ Locate dump · 1.4s`, `✓ Download · 1:36` (or `0.0s` cached), `✓ Schema setup · 1.7s`, `✓ Import tables · 7:20`, `✓ Schema finalize · 7:01`.
  - No live progress row from a previous phase lingers into the next phase.
- **Verbose run** (`-v`): full httpx chatter returns; phase banners + footers are unchanged.
- **Idempotency re-run** (run a second time against the same DB): banners + footers still print; `_run_file` skips already-applied phases, so phases 3 and 5 finish in <1 s; the `Archive … already imported — skipping.` log appears in phase 4.

## Files modified

- `src/musicbrainz_database_setup/ui/__init__.py` — new, empty package marker.
- `src/musicbrainz_database_setup/ui/phases.py` — new, `RunPhase` enum (action-oriented labels) + `PHASE_ORDER` + `format_elapsed` + `format_size` + `phase_section` context manager.
- `src/musicbrainz_database_setup/logging.py` — promotes `httpx` + `httpcore` to DEBUG only under `-v`; sets `RichHandler(show_level=False)` to hide the leading INFO column; new `_SeverityRichHandler` re-adds `Warning:` / `Error:` text labels for WARNING / ERROR records so severity stays readable when colour is stripped.
- `src/musicbrainz_database_setup/progress.py` — drops `MofNCompleteColumn` from the shared `Progress`.
- `src/musicbrainz_database_setup/cli.py` — wraps `run` / `download` / `schema_create` / `import_` in `phase_section`; collapses `run`'s two `progress_session()` blocks; logs Mirror / SQL ref / Selected dump / Local cache inside Locate dump; logs `Downloading N file(s): …` at the head of Download; removes redundant trailing `typer.echo` lines.
- `src/musicbrainz_database_setup/mirror/download.py` — `pm.remove_task` in `finally` so the progress row vanishes on completion; logs `✓ Downloaded <archive> · <size>` on success.
- `src/musicbrainz_database_setup/schema/orchestrator.py` — drops the `Running %s` log; rewrites the completion log to `✓ Applied %s · %.1fs`.
- `src/musicbrainz_database_setup/importer/copy.py` — removes the indeterminate parent task; adds the `Importing tables from <archive>` header, `✓ Imported … · N tables · M:SS` footer, and a per-table `✓ Table <schema>.<table> · <size>` log on each successful COPY; un-indents per-table COPY descriptions.
- `tests/unit/test_ui_phases.py` — new, seven tests (PHASE_ORDER, label pinning, `format_elapsed` boundaries, `format_size` units, banner-on-entry, footer-on-success, no-footer-on-exception).
- `tests/unit/test_logging.py` — new, three tests for httpx silencing at each verbosity level.
- `CHANGELOG.md` — `### Changed` bullets under `## 2026-04-25` linking the plan, this feature doc, and both session transcripts.
- `README.md` — short note in the "Supported commands" section about the phase headers + body content + `-v`-gated httpx output.
- `docs/plans/2026-04-25-progress-ui-phases.md` — plan.
- `docs/sessions/2026-04-25-progress-ui-phases-planning-session.md` — planning transcript.
- `docs/sessions/2026-04-25-progress-ui-phases-implementation-session.md` — implementation transcript.
