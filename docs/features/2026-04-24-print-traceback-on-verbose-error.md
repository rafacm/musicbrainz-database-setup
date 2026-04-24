# Print Rich traceback on error when `-v` is set

**Date:** 2026-04-24

## Problem

`cli._handle_errors` catches every `MBSetupError`, prints it as a single red line, and exits with the error's numeric code. That is the right default — it keeps the transcript clean for the 90 % case. But when the real failure is several layers deep (e.g. an `httpx.ConnectError` wrapping `OSError(9, "Bad file descriptor")` raised from `httpcore._backends.sync.connect_tcp`), the bare message is unactionable. The user can't tell whether it's httpx, SSL, psycopg, Rich, the kernel, or the network without re-running under a debugger or adding `print` statements.

The existing `-v` / `--verbose` flag sets the root logger to `DEBUG` (`logging.py:22`), so third-party libraries like `httpx` become chatty. It does **not** change error formatting in `_handle_errors`, so even at `-v` the exception collapses to the same single line.

## Changes

One behavioural tweak and one regression test set:

| Change | File | Effect |
|---|---|---|
| Traceback on DEBUG | `src/musicbrainz_database_setup/cli.py` | `_handle_errors` now calls `Console.print_exception(show_locals=False)` after the red `Error:` line when `logging.getLogger().getEffectiveLevel() <= logging.DEBUG`. Rich renders the traceback with the `__cause__` chain inline, so `raise NetworkError(...) from exc` surfaces both the wrapper and the underlying httpx / OS error. Default and `--quiet` output are unchanged. |
| Regression tests | `tests/unit/test_cli.py` (new) | Two pytest cases, one at INFO level (no traceback) and one at DEBUG level (traceback with chained cause). Both assert that `SystemExit.code == MBSetupError.exit_code`. |

No surface change: the `-v` flag continues to mean "root logger DEBUG". This change just makes that flag meaningful for error diagnosis, not just log chatter.

## Key parameters

None. The DEBUG threshold is the existing `logging` module constant; `show_locals=False` is deliberately off to avoid leaking credentials (DB URLs, PGPASSWORD) into the terminal.

## Verification

- `uv run pytest -q` — 32/32 pass (30 prior + 2 new).
- `uv run mypy src/` — strict, clean.
- `uv run ruff check src/` — clean.
- **Default run** (reproduces pre-change behaviour):

  ```
  uv run musicbrainz-database-setup run --db <url> --modules core --latest
  ```

  On a deliberately unreachable GitHub ref (e.g. blocked by firewall), stderr shows one red `Error: GET … failed: …` line and no traceback. Exit code 2 (NETWORK).

- **Verbose run:**

  ```
  uv run musicbrainz-database-setup -v run --db <url> --modules core --latest
  ```

  Same red `Error:` line is followed by a Rich-formatted traceback that walks from `cli._handle_errors → sql.github.fetch → httpx … → httpcore._backends.sync.connect_tcp → socket.create_connection`, plus the `The above exception was the direct cause of …` chain and the wrapped `OSError(9, 'Bad file descriptor')`. Exit code is still 2.

- **End-to-end run** (cached `mbdump.tar.bz2`, `postgres:17-alpine` tuned, `core` module) completed `All done.`, exit 0 — no behavioural change on the happy path.

## Files modified

- `src/musicbrainz_database_setup/cli.py` — `_handle_errors` additionally calls `Console.print_exception` when root logger level ≤ DEBUG.
- `tests/unit/test_cli.py` — new file; two tests pin the INFO-vs-DEBUG contract.
- `CHANGELOG.md` — `### Added` bullet under `## 2026-04-24`, linking the plan, this feature doc, and both session transcripts.
- `docs/plans/2026-04-24-print-traceback-on-verbose-error.md` — plan.
- `docs/sessions/2026-04-24-print-traceback-on-verbose-error-planning-session.md` — planning transcript.
- `docs/sessions/2026-04-24-print-traceback-on-verbose-error-implementation-session.md` — implementation transcript.
