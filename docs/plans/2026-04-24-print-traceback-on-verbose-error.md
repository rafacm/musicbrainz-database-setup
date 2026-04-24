# Print Rich traceback on error when `-v` is set

**Date:** 2026-04-24

## Context

A live debugging session surfaced the CLI's error-reporting blind spot. The user ran the end-to-end `run` command against a fresh `postgres:17-alpine` and saw only:

```
Error: GET https://raw.githubusercontent.com/metabrainz/musicbrainz-server/<sha>/admin/sql/Extensions.sql failed: [Errno 9] Bad file descriptor
```

`_handle_errors` in `cli.py` catches `MBSetupError`, prints it as a single red line via `Console.print(...)`, and calls `sys.exit(exc.exit_code)`. That deliberately keeps default output terse, but it also drops the traceback **and** the `__cause__` chain. `[Errno 9] Bad file descriptor` in isolation could be httpx, httpcore, SSL, psycopg, Rich, or the OS — no way to tell which.

`-v` already wires the root logger to `DEBUG` (`logging.py:22`), so a third-party library like httpx becomes verbose. It does **not** change how `_handle_errors` formats the exception itself, so the same single line comes out at `-v` too.

The real root cause turned out to be a firewall rule silently blocking `raw.githubusercontent.com`. But the time lost on speculative fixes (lazy `pm.start()`, pre-fetching SQL files outside the progress session, singleton resets) was directly traceable to not having a traceback on hand. A ~5-line change to `_handle_errors` makes the next incident diagnosable immediately.

## Plan

### 1. Show the full traceback under `-v`

File: `src/musicbrainz_database_setup/cli.py`, `_handle_errors` (around lines 326–335)

- Read the level via `logging.getLogger().getEffectiveLevel() <= logging.DEBUG` rather than re-plumbing `verbose` through Typer. The global flag already sets the root logger's level — reusing it keeps CLI surface unchanged.
- After the existing single-line `Error:` print, call `console.print_exception(show_locals=False)` when the level is `DEBUG`. Rich's traceback renders `__cause__` chains inline, so `raise NetworkError(...) from exc` at `sql/github.py:58` surfaces both the wrapper and the original httpx / OS error.
- Keep `sys.exit(exc.exit_code)` — exit semantics are identical.
- Default and `--quiet` paths are unchanged: one red line, no traceback.

### 2. Regression tests

File: `tests/unit/test_cli.py` (new)

Two tests pin the contract:
- `test_handle_errors_prints_single_line_in_info_mode` — INFO-level root logger; `NetworkError("boom")` inside `with _handle_errors():` produces stderr that contains `Error:` and `boom` but not `Traceback`; `SystemExit.code == ExitCode.NETWORK`.
- `test_handle_errors_prints_traceback_in_debug_mode` — DEBUG-level root logger; `NetworkError("boom") from ValueError("inner cause")` produces stderr containing `Error:`, the chained `inner cause`, and `Traceback`; exit code unchanged.

Fixture resets `musicbrainz_database_setup.logging._console` so Rich binds to the capsys-patched `sys.stderr` instead of the module-level cached Console from an earlier test.

### Out of scope (deliberately)

The original debugging session also sketched lazy `pm.start()` in `progress_session()`, singleton resets, and pre-fetching SQL files outside the Rich `Live` context. All three were hypotheses targeting the EBADF symptom; once the firewall was identified as the root cause, those changes became speculative and were reverted before PR. This plan does **not** carry them.

## Files touched

- `src/musicbrainz_database_setup/cli.py` — extend `_handle_errors` (≈5 net lines).
- `tests/unit/test_cli.py` — new, 2 tests.
- `CHANGELOG.md` — one `### Added` bullet under `## 2026-04-24`, linking this plan, feature doc, and both session transcripts.
- `docs/plans/`, `docs/features/`, `docs/sessions/` — this plan plus matching feature doc and planning / implementation session transcripts.

## Reused existing code

- `get_console()` (`logging.py:12-16`) — already the Rich `Console` for error output.
- `logging.getLogger().getEffectiveLevel()` — no change to `configure()`.
- `Console.print_exception` — Rich's standard traceback renderer; handles `__cause__` / `__context__`.
