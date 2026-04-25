# Implementation session — Polish CLI progress UI (phase model + visual surface)

**Date:** 2026-04-25

**Session ID:** c282e150-9312-4076-9111-3e1b3b898bef

## Summary

Implemented the approved plan: introduced a five-phase model, wired it into `cli.run()` and every standalone subcommand, gated `httpx`/`httpcore` INFO chatter behind `-v`, compacted per-SQL-file output to a single `✓ X (N.Ns)` completion line, and replaced the indeterminate `Import mbdump.tar.bz2 0/?` parent task with proper header/footer log lines around the unchanged per-table COPY bars. Added eight unit tests (`test_ui_phases.py`, `test_logging.py`); all 40 tests pass; ruff and mypy `--strict` are clean.

One mid-flight course correction: the plan originally proposed adding a `transient` kwarg to `ProgressManager.add_task` so spinner tasks would vanish on completion. While implementing it turned out the existing `try/finally + pm.remove_task(...)` pattern in `schema/psql.py` already does exactly that — the kwarg would have been redundant. Reverted that change before continuing.

## Detailed conversation

### User

Plan approved (see paired planning-session document).

### Assistant

Created task list with 10 items (branch → ui/phases → logging silencing → progress kwarg → orchestrator/psql → importer/copy → cli wiring → tests → lint/type/test → docs) and switched to a `feature/progress-ui-phases` branch off main.

### Assistant — `ui/phases` module

Created `src/musicbrainz_database_setup/ui/__init__.py` (empty package marker) and `src/musicbrainz_database_setup/ui/phases.py` with:

- `RunPhase(StrEnum)` — five members: `MIRROR`, `DOWNLOAD`, `SCHEMA_PRE`, `IMPORT`, `SCHEMA_POST`, mapped to display labels `"Mirror"`, `"Download"`, `"Schema (pre)"`, `"Import"`, `"Schema (post)"`.
- `PHASE_ORDER` — `tuple[RunPhase, ...]` listing the five members in pipeline order.
- `format_elapsed(seconds: float) -> str` — `0.1s` for sub-minute, `M:SS` for ≥ 60 s. Avoids the awkward `124.7s` reading for multi-minute DDL phases.
- `@contextmanager phase_section(phase, *, total_phases=len(PHASE_ORDER))` — derives a 1-indexed banner index from `PHASE_ORDER.index(phase)+1`; on entry calls `get_console().rule(f"Phase {idx}/{total} · {phase.value}", style="bold cyan")`; on successful exit emits `log.info("✓ %s · %s", phase.value, format_elapsed(elapsed))`. No `try/finally` wrapping the footer — the spec is "no footer on exception", so a bare `yield` followed by the log line gives that for free.

### Assistant — httpx silencing in `logging.configure`

Edited `src/musicbrainz_database_setup/logging.py` to add, immediately after the root logger level is set:

```python
http_level = logging.DEBUG if verbose else logging.WARNING
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(http_level)
```

`--quiet` continues to use the WARNING root level, which already covers `httpx`/`httpcore` since they default to WARNING in the loop above. The `--log-file` handler is at DEBUG so it captures the full HTTP trail regardless of console level.

### Assistant — Reverted the redundant `transient` kwarg

Started adding a `transient: bool = False` kwarg to `ProgressManager.add_task` per the plan, but on second look the existing `psql.run_sql_file` flow (`schema/psql.py:112–123`) already calls `pm.remove_task(task)` in a `finally` block — so the spinner already vanishes on completion. Adding a `transient` kwarg would have been duplicative. Reverted the change to `progress.py` and updated the corresponding task with a note on why it's not needed.

### Assistant — Compact per-SQL-file output

Edited `src/musicbrainz_database_setup/schema/orchestrator.py:_run_file`:

- Dropped `log.info("Running %s", sqlfile.repo_path)` — the `psql X.sql` spinner already shows what's running.
- Replaced `log.info("%s finished in %.1fs", sqlfile.repo_path, elapsed)` with `log.info("✓ %s (%.1fs)", sqlfile.repo_path, elapsed)`. The `✓` prefix mirrors the phase footer (`✓ Schema (pre) · 1.7s`), so successful files visually nest under the phase rule.

### Assistant — `importer/copy.py` header + footer

Removed the indeterminate parent progress task (`pm.add_task(f"Import {archive_name}", total=None, note="")` and the matching `pm.update(..., note=f"{tables_total} tables")` in the `finally` block). Replaced with:

- `log.info("Importing %s", archive_name)` at the start of the import.
- `log.info("✓ Imported %s · %d tables · %s", archive_name, tables_total, format_elapsed(elapsed))` after `conn.commit()`.

Imported `format_elapsed` from `musicbrainz_database_setup.ui.phases` — the same renderer used by the phase footer, so durations are consistent across both lines.

Removed the `archive_task_id: object` parameter from `_copy_member` since it was never used inside the body. Also dropped the `"  COPY"` leading two-space indent on the per-table description — there is no parent now to indent under.

### Assistant — CLI wiring

Edited `src/musicbrainz_database_setup/cli.py`:

- Imported `RunPhase` and `phase_section` from `musicbrainz_database_setup.ui.phases`.
- `download`: collapsed to a single `progress_session()` containing two phase sections — Mirror (resolve dir + fetch checksums) and Download (the loop). Replaced the bare `typer.echo(f"Downloading to {dest}")` with `log.info(...)` so it shows up inside the Mirror banner. Removed the trailing `typer.echo("Done.")`.
- `schema create`: respects the existing `--phase pre/post/all` flag, wrapping each leg in the relevant `RunPhase.SCHEMA_PRE` / `RunPhase.SCHEMA_POST` section. Replaced the trailing `typer.echo` with a leading `log.info("Resolved %s → %s", ref, sha[:12])` (the SHA is useful context; the closing one was redundant with the footer).
- `import`: a single `phase_section(RunPhase.IMPORT)` wrapping the loop. Removed `typer.echo("Import complete.")`.
- `run`: collapsed the two `progress_session()` blocks into one outer block. Wrapped each leg in its phase section. Logged the resolved SHA inside the Mirror phase. Removed `typer.echo("All done.")`.

Used a single `with progress_session(), phase_section(RunPhase.IMPORT):` line in `import_` so the live table starts before the banner is rendered (otherwise the rule would appear before the progress region locks in).

### Assistant — Tests

Wrote `tests/unit/test_ui_phases.py` with five tests:

1. `PHASE_ORDER` lists every `RunPhase` member in canonical order.
2. `format_elapsed` for sub-minute durations (rounding 0.05→0.1s, mid-range, edge).
3. `format_elapsed` for ≥1 minute (60→1:00, 125→2:05, 3599→59:59).
4. `phase_section` emits both the banner and the success footer when the body completes cleanly.
5. `phase_section` emits the banner but **not** the footer when the body raises.

Wrote `tests/unit/test_logging.py` with three tests pinning the httpx silencing contract: default → WARNING, verbose → DEBUG, quiet → WARNING (the root level already suppresses INFO either way, but the assertion makes the intended behaviour visible).

Both tests use a `fresh_console_and_level` (or `reset_loggers`) fixture mirroring the pattern already established in `test_cli.py` so the singleton stderr Console doesn't leak across tests.

Hit one ruff lint failure: `SIM117` in `test_ui_phases.py` — combined the nested `pytest.raises(...)` and `phase_section(...)` into a single `with` statement.

### Assistant — Verification

Ran:

```bash
uv sync --extra dev --quiet
uv run ruff check src tests   # All checks passed!
uv run mypy src               # Success: no issues found in 29 source files
uv run pytest                 # 40 passed in 0.54s
```

`uv run musicbrainz-database-setup --help` rendered correctly, all subcommands present.

### Assistant — Documentation

Wrote per AGENTS.md:

- `docs/plans/2026-04-25-progress-ui-phases.md` (a copy of the approved plan).
- `docs/features/2026-04-25-progress-ui-phases.md` (Problem / Changes / Key parameters / Verification / Files modified).
- `docs/sessions/2026-04-25-progress-ui-phases-planning-session.md` (paired planning transcript).
- This implementation transcript.
- `CHANGELOG.md` entry under `## 2026-04-25` (`### Changed`) linking the plan + feature + both transcripts.
- `README.md` short note in the "Supported commands" section about phase headers and `-v`-gated httpx output.

### User — review feedback after the first end-to-end test

After the first test run on PR #7 the user attached four screenshots and listed nine concrete refinements:

1. **Phase 1 "Mirror"** — opaque label; the user couldn't tell which mirror was being used or what the `✓ Mirror · 1.4s` footer represented.
2. **Phase 2 "Download"** — `✓ Download · 1:36` didn't say what was downloaded (one file? several?).
3. **Phase 3 "Schema (pre)"** — `(pre)` is jargon; the per-file lines (`admin/sql/Extensions.sql`) read as bare paths with no verb context. Suggested prefixing with "File" or a better user-facing label.
4. **Phase 4 "Import"** — the per-table COPY rows vanish on completion, leaving no record of what was imported. The `✓ Imported mbdump.tar.bz2 · 177 tables · 7:20` and `✓ Import · 7:20` footers were nearly identical. Suggested renaming to "Import tables".
5. **Phase 5 "Schema (post)"** — same `(post)` jargon issue; the user wanted the actual work (primary keys, indexes, constraints) to be more visible.
6. **The Download progress bar lingered** through phases 3, 4, and 5 — it stayed in the live region until the run finished.
7. **Long byte numbers** in the progress bars (raw byte counts alongside the human-readable MiB/GiB column).
8. **"INFO" prefix** on every line — the user asked whether it was a leftover from generic logging or actually load-bearing.

### Assistant — refinements

Decided on action-oriented phase labels and addressed each point:

- **Phase rename + body logs** in `ui/phases.py` and `cli.py`:
  - `MIRROR = "Locate dump"` — the body now logs `Mirror: <url>`, `SQL ref <ref> → <SHA>`, `Selected dump: <name>`, and `Local cache: <path>` so the URLs are visible inline.
  - `DOWNLOAD = "Download"` (kept) — the body now logs `Downloading N file(s): <comma-separated names>` before the loop; per-archive completion logs `✓ Downloaded <archive> · <size>` (added in `mirror/download.py`).
  - `SCHEMA_PRE = "Schema setup"` — clearer than "(pre)"; pairs with "Schema finalize".
  - `IMPORT = "Import tables"` — direct adoption of the user's suggested label; differentiates the phase footer (`✓ Import tables · 7:20`) from the per-archive line (`✓ Imported mbdump.tar.bz2 · 177 tables · 7:20`).
  - `SCHEMA_POST = "Schema finalize"` — explicit about its role (keys, indexes, constraints, triggers) without enumerating every file in the label.
- **Per-DDL-file label** in `schema/orchestrator.py:_run_file`: completion log changed from `✓ admin/sql/Extensions.sql (0.1s)` to `✓ Applied admin/sql/Extensions.sql · 0.1s` — explicit verb prefix, middle-dot separator that visually pairs with phase footers.
- **Per-table import log** in `importer/copy.py:_copy_member`: each successful COPY now emits `✓ Table <schema>.<table> · <size>` so the imported table list is durable in scrollback (177 lines for a core import — useful, not noisy). Per-archive header changed to `Importing tables from <archive>` to match the phase label.
- **Lingering download row** in `mirror/download.py`: added `pm.remove_task(task_id)` in a `finally` block. The progress row now disappears the moment the archive verifies and gets renamed.
- **MofN column drop** in `progress.py`: removed `MofNCompleteColumn`. For byte-based tasks the `DownloadColumn(binary_units=True)` already shows progress in human units; the M-of-N column was duplicating the same totals as raw byte counts (the long numbers the user objected to).
- **INFO prefix removed** in `logging.py`: set `RichHandler(show_level=False)`. Verified Rich still styles WARNING / ERROR message bodies in their per-level colours (yellow / red) so severity remains visible without the textual label. Confirmed via the existing test_cli.py traceback test which still passes (the assertion is on the message body, not the level prefix).
- **`format_size` helper** added to `ui/phases.py` so the per-table and per-archive size logs use the same vocabulary as Rich's progress column.

### Assistant — test updates

Extended `tests/unit/test_ui_phases.py` with two new tests:
- `test_phase_labels_are_action_oriented` pins each enum value to the new label so a casual rename surfaces in code review.
- `test_format_size_uses_binary_units` covers each unit transition (B → KiB → MiB → GiB → TiB).

Updated existing assertions for `Schema (pre)` → `Schema setup` and `Import` → `Import tables`.

### Assistant — verification

```
uv run ruff check src tests   # All checks passed!
uv run mypy src               # Success: no issues found in 29 source files
uv run pytest -q              # 42 passed in 0.53s
```

Updated CHANGELOG, README, this implementation transcript, and the feature doc to reflect the refined phase labels and the additional UX changes.

### User — Evil Martians article review

> Review the current CLI UX against the guidelines in this article https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays

### Assistant — review

Fetched the article via `WebFetch` and extracted 15 concrete guidelines across the three patterns (spinners, X of Y, progress bars) plus an output/logging cluster. Reported a per-guideline assessment back to the user with pass/partial/fail markers, then proposed five concrete follow-up items sorted by impact/effort:

1. Add `(N/total)` count prefix on per-DDL-file and per-archive log lines.
2. Colour the `✓` symbol bold green via a Rich Highlighter (no markup in messages so `--log-file` stays clean).
3. Reword phase footer to past-tense `✓ <label> complete · <elapsed>` so it reads grammatically for noun labels.
4. Add a global `--no-color` flag (Typer callback) that sets `NO_COLOR=1` before Console init.
5. Sort out `pg_stat_progress_*` polling for slow DDL — out of scope for this PR, file an issue.

### User — direction

> yes. For 6 create an issue with the details so we can tackle it in the future

### Assistant — round-2 implementation

- **(N/total) prefix.** Threaded `index` / `total` kwargs through `Orchestrator._run_file`, `download_archive`, and `import_archive`. CLI call sites materialize the file/archive manifests with `list(...)` and call with `enumerate(..., start=1)`. Per-table COPY lines deliberately stay count-less because `tarfile.open(mode="r|bz2")` is streaming-only and can't enumerate members up-front.
- **Green checkmark.** Wrote `_CheckmarkHighlighter(Highlighter)` in `logging.py` and attached it via `RichHandler(highlighter=…)`. Walks `Text.plain`, calls `text.stylize("bold green", i, i+1)` for each `✓`. The log message string stays plain so the file handler gets `✓` literal — verified by reading the existing `--log-file` formatter (no markup parsing).
- **Past-tense footer.** One-line change in `ui/phases.py:phase_section`: `"✓ %s · %s"` → `"✓ %s complete · %s"`. Updated the two assertions in `test_ui_phases.py`.
- **`--no-color` flag.** Added a `no_color: bool` kwarg to `configure()`; sets `os.environ["NO_COLOR"] = "1"` and calls a new `_reset_console()` helper *before* constructing the RichHandler, because Rich reads the env var only at `Console.__init__`. The CLI global callback gained a matching `--no-color` Typer option. New `test_logging.py` tests pin both the flag (`Console.no_color is True`) and the default leaving the env var untouched.

### Assistant — verification

```
uv run ruff check src tests   # All checks passed!
uv run mypy src               # Success: no issues found in 29 source files
uv run pytest -q              # 44 passed in 0.60s
```

### Assistant — issue filing for slow-DDL progress polling

Created [issue #8](https://github.com/rafacm/musicbrainz-database-setup/issues/8) — "Show real progress for slow DDL phases via `pg_stat_progress_*` polling" — covering the existing `psql.py:108-111` TODO comment with a concrete proposal: open a side psycopg connection, poll `pg_stat_progress_create_index` once per second while a DDL spinner is active, surface the inner phase + `blocks_done/blocks_total` into the Rich task description. Caveat noted: not every DDL has a progress view (only CREATE INDEX, VACUUM, ANALYZE, COPY, CLUSTER, BASE_BACKUP, CREATE_INDEX). Linked to the PostgreSQL [Progress Reporting docs](https://www.postgresql.org/docs/current/progress-reporting.html).

### User — Homebrew-style banner

> When using brew, I see it used "==> " as an indicator for phases. Like in "==> Fetching downloads for: agg" […] Is this something we could use here? Instead of the line that occupies the whole width of the terminal?

(Screenshot shows brew's `==>` marker in bold blue, plus bold message text, e.g. `==> Fetching downloads for: agg`, `==> Pouring agg--1.7.0.arm64_tahoe.bottle.tar.gz`.)

### Assistant — round-3 implementation

Replaced the full-width `Console.rule(...)` banner with a single-line `==>` prefix:

- `ui/phases.py:phase_section`: changed entry from `console.rule(f"Phase {idx}/{total} · {phase.value}", style="bold cyan")` to `console.print(f"[bold blue]==>[/] [bold]Phase {idx}/{total} · {phase.value}[/]")`. Same content, but the marker now fits in any terminal width and reads as part of the log stream rather than a section break. Rich strips the markup automatically under `--no-color` / non-TTY, so the plain-text fallback is `==> Phase 1/5 · Locate dump`.
- Updated `tests/unit/test_ui_phases.py` to assert `"==>"` is in the captured stderr — pins the marker so a future style revert surfaces in CI.

Lint + types + tests still clean; 44 / 44 pass.
