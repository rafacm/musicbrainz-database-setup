# Polish CLI progress UI — phase model + visual surface

**Date:** 2026-04-25

## Context

The end-to-end `run` command already does the right work but the screen output flattens five very different stages into one stream of `INFO` lines and a couple of progress bars. The screenshot from the 2026-04-23 successful import shows:

- `httpx` `HTTP Request: GET …` lines leaking into INFO from `httpx`'s default logger.
- Per-SQL-file pairs of `Running admin/sql/X.sql` + `admin/sql/X.sql finished in 0.1s`.
- A parent progress bar `Import mbdump.tar.bz2  0/?  0/? bytes  ?  0:00:51` (indeterminate, looks broken).
- A child bar per `COPY musicbrainz.<table>` while the archive is processed.

There is no visual indication of which **phase** of the pipeline the user is in, no overall progress through the run, and a lot of redundant / misleading output. AGENTS.md already names the stages implicitly (Mirror → Download → Schema-pre → Import → Schema-post); we want to elevate that to a first-class concept and clean up the noise.

Goal: scan-friendly output that answers "where am I in the run?" at a glance, while keeping `-v` as the escape hatch for full diagnostic chatter.

## The 5 phases

| # | Label          | Code reached                                                      | Per-step work                  |
|---|----------------|-------------------------------------------------------------------|--------------------------------|
| 1 | Mirror         | `github.resolve_ref` + `_resolve_dump_dir` + `dl.fetch_checksums` | A few HTTP HEAD/GETs           |
| 2 | Download       | `dl.download_archive` loop                                        | One bar per archive            |
| 3 | Schema (pre)   | `Orchestrator.run_pre_import`                                     | One spinner per SQL file       |
| 4 | Import         | `import_archive` loop                                             | Per-archive header + per-table |
| 5 | Schema (post)  | `Orchestrator.run_post_import`                                    | One spinner per SQL file       |

Sub-steps (individual SQL files, individual COPY tables) are **not** phases — they are work items shown inside the parent phase via existing progress tasks and a single completion log line.

## Approach

### 1. New `ui/phases.py` module

```python
class RunPhase(StrEnum):
    MIRROR        = "Mirror"
    DOWNLOAD      = "Download"
    SCHEMA_PRE    = "Schema (pre)"
    IMPORT        = "Import"
    SCHEMA_POST   = "Schema (post)"

PHASE_ORDER = (RunPhase.MIRROR, RunPhase.DOWNLOAD, RunPhase.SCHEMA_PRE,
               RunPhase.IMPORT, RunPhase.SCHEMA_POST)

@contextmanager
def phase_section(phase: RunPhase, *, total_phases: int = len(PHASE_ORDER)) -> Iterator[None]:
    """Emit a banner on entry and an elapsed-time line on exit."""
```

Behaviour:
- On entry: `console.rule(f"Phase {idx}/{total} · {phase.value}", style="bold cyan")` via the shared stderr `Console`. Index is derived from `PHASE_ORDER`.
- On exit (success): a single `log.info("✓ %s · %s", phase.value, format_elapsed(elapsed))`.
- On exit (exception): no extra line — `_handle_errors` already prints the red `Error:` and (with `-v`) traceback. Banner already in scrollback tells the user which phase failed.

The helper is a no-op-friendly: standalone subcommands (`download`, `schema create --phase pre`, `import`) wrap themselves in just the relevant phase and the banner makes sense even outside `run`.

### 2. Wire phases into `cli.run()`

Wrap each pipeline step in `phase_section`. Collapse the two `progress_session()` blocks into one outer block so the Rich Live table stays alive across phases (avoids the bars flickering between phase 2 and phases 3–5). `connect()` still scopes the DB connection.

Also wrap the standalone subcommands so they each emit their relevant phase banner: `cli.download` → `RunPhase.MIRROR` then `RunPhase.DOWNLOAD`, `cli.schema_create` → `RunPhase.SCHEMA_PRE` / `SCHEMA_POST` based on the `--phase` flag, `cli.import_` → `RunPhase.IMPORT`.

### 3. Quiet `httpx` and `httpcore` at default verbosity

In `logging.configure()` (`logging.py`), promote `httpx` and `httpcore` to DEBUG only when `-v` is set; otherwise WARNING. The default screen no longer shows `HTTP Request: GET …` for every SQL fetch / SHA256SUMS / GitHub call. The `--log-file` handler is at DEBUG so it always captures everything regardless of console level.

### 4. Compact per-SQL-file output

`schema/orchestrator.py:_run_file` previously emitted `Running X` + `X finished in 0.1s`, *and* `psql.run_sql_file` showed a spinner task. Drop the "Running …" log; rewrite the completion log to `✓ X (N.Ns)` so it lines up with the phase footer. The psql spinner already vanishes on completion via the existing `try/finally + remove_task` pattern — no extra work needed there.

### 5. Fix the misleading `Import mbdump.tar.bz2 0/?` parent task

In `importer/copy.py`, the indeterminate parent task with `total=None` rendered as `0/?  0/? bytes  ?  0:00:51` — looks like a broken bar. Replace it with a single `log.info("Importing %s", …)` header at archive start, plus a final `log.info("✓ Imported %s · %d tables · %s", …)` on success. Per-table bars stay as they are (those work well — bytes total is known per member). Drop the `"  COPY"` two-space indent now that there is no parent.

### 6. Remove the redundant trailing `typer.echo` lines

The phase footer already says it. Drop `typer.echo("All done.")` from `run`, the `Import complete.` line from `import_`, the `Done.` from `download`, and the `Schema phase … complete (…)` from `schema_create`.

## Files to modify

- `src/musicbrainz_database_setup/ui/phases.py` — **new**, RunPhase enum + `phase_section` context manager.
- `src/musicbrainz_database_setup/ui/__init__.py` — **new**, empty.
- `src/musicbrainz_database_setup/logging.py` — silence `httpx` / `httpcore` at default verbosity.
- `src/musicbrainz_database_setup/cli.py` — wrap `run()` and standalone subcommands in `phase_section`; collapse the two `progress_session()` blocks into one; drop `typer.echo` redundant lines.
- `src/musicbrainz_database_setup/schema/orchestrator.py` — drop "Running …" log; rewrite "finished in" log to `✓ X (N.Ns)`.
- `src/musicbrainz_database_setup/importer/copy.py` — drop indeterminate parent task; add header + completion log lines; drop the two-space indent on per-table COPY descriptions.
- `tests/unit/test_ui_phases.py` — **new**, unit tests for `RunPhase`, `format_elapsed`, and `phase_section`.
- `tests/unit/test_logging.py` — **new**, asserts `httpx` logger is set to WARNING by default and DEBUG with `verbose=True`.

Reuse: existing `get_console()` (logging.py:12), `ProgressManager.instance()` (progress.py:51), `console.rule()` from Rich. No new dependencies.

## Documentation (per AGENTS.md)

- `docs/plans/2026-04-25-progress-ui-phases.md` — this file.
- `docs/features/2026-04-25-progress-ui-phases.md` — Problem / Changes / Key parameters / Verification / Files modified.
- `docs/sessions/2026-04-25-progress-ui-phases-planning-session.md` and `…-implementation-session.md`.
- `CHANGELOG.md` — under today's date, a `### Changed` entry pointing to the plan + feature + both transcripts.
- `README.md` — small note in the "Supported commands" section showing the new phase headers; mention that `httpx` chatter is now `-v`-gated.

## Verification

End-to-end happy path (most important — the screenshot scenario):

```bash
uv run musicbrainz-database-setup run \
  --modules core --latest \
  --workdir /tmp/mb-cache --yes
```

Expected on stderr (default verbosity):

1. Five clearly-separated `Phase N/5 · …` rules in order.
2. No `httpx` `HTTP Request: GET …` lines.
3. No `Running admin/sql/X.sql` lines.
4. One `✓ admin/sql/X.sql (N.Ns)` line per file in phases 3 and 5.
5. No `Import mbdump.tar.bz2 0/?  0/? bytes` row — only per-table COPY bars.
6. A single `✓ Imported mbdump.tar.bz2 · N tables · M:SS` line on archive completion.

Then verify `-v` still gives full chatter (httpx + DEBUG):

```bash
uv run musicbrainz-database-setup -v run --modules core --latest --yes
```

Idempotency check (re-run on already-applied DB):

```bash
uv run musicbrainz-database-setup run --modules core --latest --yes  # second time
```

Expect each phase to still emit its banner + footer; the `Skipping …` debug lines from `_run_file` only appear under `-v`.

Lint + type + tests:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest
```
