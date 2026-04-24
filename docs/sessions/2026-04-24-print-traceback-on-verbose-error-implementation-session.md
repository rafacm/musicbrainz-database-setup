# Implementation session — Print Rich traceback on error when `-v` is set

**Date:** 2026-04-24

**Session ID:** 0c103ea4-8fba-42b2-ad6c-25aa1224b070

## Summary

Implemented the plan under auto mode. The change to `_handle_errors` landed cleanly in one edit; the cosmetic progress-bar fix required a `clear_tasks()` helper and a call from `progress_session()`. After asking the user to rerun with `-v`, the traceback surfaced `httpcore._backends.sync.connect_tcp → socket.create_connection → OSError(9, 'Bad file descriptor')` — a kernel-level bad-fd error, not a httpx bug.

A long series of speculative hypotheses followed — pre-fetching SQL files outside the progress session to avoid Rich `Live` + httpx interaction, lazy `pm.start()` so an empty progress session never spawns a `Live` at all — each targeting a pattern that *fit* the symptoms. Each was guarded with tests + lint and pushed, but none were the real fix. The user then reported it was a firewall rule silently blocking `raw.githubusercontent.com`. With that, all the speculative changes were reverted; only the `-v` traceback fix (originally proposed as pure diagnostics) survived. An end-to-end verification run against a fresh `postgres:17-alpine` completed `All done.`, exit 0.

A PR was opened (#6) with just the traceback change. Code review flagged two gaps: (a) the CHANGELOG entry needed links to plan + feature + session transcripts per `AGENTS.md`, and (b) the behaviour needed automated regression coverage, not manual checks. This document + the new plan + feature doc + a `tests/unit/test_cli.py` regression suite are that follow-up.

## Detailed conversation

### User

(User approved the plan via the plan-mode UI, switching to auto mode.)

### Assistant

Edited `cli.py::_handle_errors` (around line 327) to capture the console once, print the existing red `Error:` line, and — when `logging.getLogger().getEffectiveLevel() <= logging.DEBUG` — follow it with `console.print_exception(show_locals=False)`. `show_locals=False` deliberately avoids dumping DB URLs or PGPASSWORD into the terminal.

Edited `progress.py` to add `ProgressManager.clear_tasks()` (iterating `self._progress.task_ids` and calling `remove_task` on each) and called it from `progress_session()`'s `finally` block after `stop()`.

Ran `uv run pytest -q`, `uv run mypy src/`, `uv run ruff check src/` — all green (30 tests, mypy strict clean, ruff clean). Told the user to rerun with `-v` to surface the traceback.

### User

> Ummm... I am getting an error that the "-v" option does not exist when running your proposed command?
>
> ```
> uv run musicbrainz-database-setup run \
>   --db postgresql://postgres:postgres@localhost:5432/postgres \
>   --modules core --latest -v
> ```
> Usage: musicbrainz-database-setup run [OPTIONS]
> Error: No such option: -v

### Assistant

`-v` is a global option on the Typer app callback (`cli.py:90-101`), not on the `run` subcommand. It has to come **before** the subcommand. Corrected the invocation: `uv run musicbrainz-database-setup -v run ...`.

### User

> This the output: [long DEBUG-level output + full Rich traceback]
>
> ```
> DEBUG    connect_tcp.started host='raw.githubusercontent.com' port=443 local_address=None timeout=30.0 socket_options=None
> DEBUG    connect_tcp.failed exception=ConnectError(OSError(9, 'Bad file descriptor'))
> Error: GET https://raw.githubusercontent.com/… failed: [Errno 9] Bad file descriptor
> … traceback showing ConnectError at httpcore/_backends/sync.py:207 → socket.create_connection …
> NetworkError: GET https://raw.githubusercontent.com/… failed: [Errno 9] Bad file descriptor
> ```

### Assistant

The traceback nailed the failure to `socket.create_connection` inside httpcore, **not** inside httpx or SSL. Noted the successful calls (api.github.com, data.metabrainz.org × 2) all happened *outside* the progress session, whereas this one was the first httpx call inside the second `progress_session()`. Hypothesised the Rich `Live` singleton `stop()` / `start()` cycle was corrupting fd state on macOS + Python 3.12.

Proposed a pragmatic workaround: pre-fetch all `admin/sql/*.sql` files **before** opening `connect(db) + progress_session()`, so the orchestrator's `github.fetch` calls hit the on-disk cache (`sql/github.py:47 if dest.exists(): return dest`) and never touch httpx under Rich. Also a UX win: fails fast on GitHub outage before any DB work.

Edited `cli.py::run` to loop over `manifest.pre_import_files(mods) + manifest.post_import_files(mods)` and warm the cache before the DB-and-progress block. Ran the full check suite (pytest / mypy / ruff) — green. Asked the user to rerun.

### User

> I am getting now:
>
> ```
> INFO     HTTP Request: GET https://api.github.com/… 200 OK
> INFO     HTTP Request: GET …/LATEST 200 OK
> INFO     HTTP Request: GET …/SHA256SUMS 200 OK
> INFO     Archive mbdump.tar.bz2 already present and verified.
> Error: GET https://raw.githubusercontent.com/… failed: [Errno 9] Bad file descriptor
> ```

### Assistant

The prefetch itself fails with EBADF, and it's now outside the progress session. So the trigger isn't "httpx during Rich Live" — it's "any httpx call after a `pm.start()` / `pm.stop()` cycle fails". Today's run differs from yesterday's successful one in exactly one way: the archive is cached, so `download_archive` returned early without adding a progress task. The `progress_session()` around downloads started and stopped a Rich `Live` with **zero** tasks.

Refined hypothesis: **empty `Progress.start()` / `stop()` cycle poisons the next httpx socket on macOS + Python 3.12**. Fix: make `progress_session()` lazy — drop the eager `pm.start()` on entry. `ProgressManager.add_task()` already calls `self.start()` internally, so an empty session never spawns a `Live`; a session with real tasks works as before.

Edited `progress.py::progress_session` to remove the eager `pm.start()` call (kept `stop()` + `clear_tasks()` in `finally`, both idempotent if `Live` was never started). Ran pytest / mypy / ruff — green. Asked the user to rerun.

### User

> Wait. It was an issue with my firewall

> I believe I have fixed it. Let me try...

### Assistant

Deleted the in-progress project-memory file that was about to bake the "empty Rich Live poisons httpx" theory into permanent memory — that conclusion is wrong if the firewall was the cause.

Summarised the open decisions for after the rerun:

1. `-v` traceback in `_handle_errors` — keep (useful regardless).
2. `clear_tasks()` call in `progress_session()` — keep if "Download shown twice" was a real bug; revert if it was a crash-path side-effect.
3. Lazy `pm.start()` — motivated solely by the EBADF theory; leaned revert.
4. SQL prefetch — same; leaned revert.

### User

> You can start the Docker container and run the command yourself to verify

### Assistant

Started a tuned `postgres:17-alpine` container (`-c shared_buffers=2GB -c max_wal_size=8GB -c checkpoint_timeout=30min -c effective_io_concurrency=200 -c random_page_cost=1.1`), waited for `pg_isready`, launched the full end-to-end `run` in the background, and armed a `Monitor` tailing the output with a grep for success, error, phase-start, and phase-finish markers.

The run completed with `All done.`, exit 0. Per-phase timings:

| Phase | Duration |
|---|---|
| `Extensions.sql` | 0.1 s |
| `CreateCollations.sql` | 0.1 s |
| `CreateSearchConfiguration.sql` | 0.0 s |
| `CreateTypes.sql` | 0.0 s |
| `CreateTables.sql` | 0.3 s |
| COPY (implicit) | ~7 m |
| `CreatePrimaryKeys.sql` | 46.0 s |
| `CreateFunctions.sql` | 0.1 s |
| `CreateIndexes.sql` | 182.9 s |
| `CreateFKConstraints.sql` | 345.7 s |
| `CreateConstraints.sql` | 257.2 s |
| `SetSequences.sql` / `CreateViews.sql` / `CreateTriggers.sql` | <0.3 s each |

Total wall time ~21 min — consistent with the 2026-04-23 baseline. Reverted the speculative fixes (lazy `pm.start()`, `clear_tasks()` method + call, SQL prefetch loop). Final net diff on the branch: 4 lines in `cli.py::_handle_errors`. Re-ran the check suite — green.

### User

> Create a PR for this work.

### Assistant

Read `AGENTS.md` for branching rules (dedicated branch off `main`, rebase-only merge strategy) and changelog format. Pulled `main` with stashed diff, created branch `fix/print-traceback-on-verbose-error`, added a one-line `### Added` entry under `## 2026-04-24` in `CHANGELOG.md`. Committed with a descriptive `fix(cli): …` message, pushed with `-u`, and opened PR #6 via `gh pr create` with a summary + test-plan body.

### User

> Review the PR comments

### Assistant

Fetched the two code-review comments via `gh api repos/rafacm/musicbrainz-database-setup/pulls/6/comments`:

1. `CHANGELOG.md:17` — changelog entry doesn't meet the repo's release-note requirements (no links to plan / feature / session transcripts, and those documents aren't in the PR).
2. `src/musicbrainz_database_setup/cli.py:333` — missing automated regression test for verbose vs. non-verbose behaviour.

Created this implementation session doc, a paired planning-session doc, a plan, and a feature doc to satisfy (1). Extended the changelog bullet to link all four. For (2), added `tests/unit/test_cli.py` with two tests: `test_handle_errors_prints_single_line_at_info_level` (captures stderr, asserts `Error:` + message but no `Traceback`) and `test_handle_errors_prints_traceback_at_debug_level` (with a chained `from ValueError("inner cause")`, asserts `Error:`, the inner message, and `Traceback` are all present). Both assert `SystemExit.code == ExitCode.NETWORK`. Used a fixture that resets `musicbrainz_database_setup.logging._console` so Rich binds to the capsys-patched `sys.stderr`.

Ran `uv run pytest -q`, `uv run mypy src/`, `uv run ruff check src/` — green. Committed the docs + test + CHANGELOG link update, pushed, and replied to both review comments with the commit SHA that addresses each.

## Decision log

- **Reverted the speculative fixes.** Lazy `pm.start()`, `clear_tasks()` call, and SQL prefetch were each motivated by a theory (Rich `Live` × httpx fd interaction) that the firewall discovery invalidated. Keeping them would carry unmotivated complexity for a bug that didn't exist.
- **Kept the `-v` traceback change.** Its value is independent of the debugging outcome — it's the tool that made the firewall discoverable, and it stays useful for the next incident.
- **Did not save project memory about "Rich Live × httpx EBADF on macOS".** The hypothesis was wrong; preserving it would mislead future sessions. Deleted the draft memory file before it could persist.
- **Wrote the docs trail post-hoc rather than arguing against it.** A 5-line CLI change is borderline for the full plan + feature + two session transcripts template, but the reviewer (the user) explicitly enforced it. The transcripts are drawn from the actual conversation, so they're factually grounded — not manufactured.
- **Tested via capsys with a module-level `_console` reset fixture.** Rich's `Console(stderr=True)` binds `sys.stderr` at construction time, so the cached singleton from `get_console()` would point at pre-capsys stderr. Resetting `logging._console = None` before the test lets the first `get_console()` call inside `_handle_errors` bind to the capsys-patched stderr.
- **Used `show_locals=False` in `print_exception`.** Default locals dumping would leak credentials (DB URLs, `PGPASSWORD` passed via env) into the terminal; `False` keeps stack frames without variable values.
