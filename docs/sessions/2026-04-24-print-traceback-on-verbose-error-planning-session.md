# Planning session — Print Rich traceback on error when `-v` is set

**Date:** 2026-04-24

**Session ID:** 0c103ea4-8fba-42b2-ad6c-25aa1224b070

## Summary

The planning phase of this change emerged from a live debugging session: the user ran the end-to-end `run` command against a fresh `postgres:17-alpine`, hit an opaque `[Errno 9] Bad file descriptor` originating from an httpx call, and couldn't tell from the single-line CLI output whether the cause was httpx, Rich's `Live` singleton, psycopg, SSL, or the OS.

Plan mode was entered mid-debug. The agreed plan had two parts: (a) expose the real traceback via a tiny `_handle_errors` change so the next incident is diagnosable first-try, and (b) also clean up a separate cosmetic progress-bar bug observed in the same screenshots (Download bar rendering twice due to the Rich `Progress` singleton re-entry). Speculative root-cause fixes for the EBADF itself were deferred to a follow-up, pending the traceback.

The user approved that plan via `ExitPlanMode`. During implementation the EBADF turned out to be a firewall rule, not a code bug, so the speculative fixes were reverted and the final PR carries only the `-v` traceback change and its test. This transcript captures the planning phase only — implementation is in the paired implementation-session document.

## Detailed conversation

### User

> Let's work on polishing the display of progress of the whole process. Let's first agree what are the phases. Currently we get "INFO" entries displayed. I've attached two screenshots:

(Screenshots show the CLI output: `INFO HTTP Request` lines from httpx, `Download mbdump.tar.bz2` Rich progress bar, `INFO Running admin/sql/*.sql` / `INFO … finished in X s` pairs, and a per-table `COPY` progress bar.)

### Assistant

Mapped the 8 distinct phases of `run` (Resolve → Verify mirror → Download → Connect → Schema · prepare → Import → Schema · finalize → Done) via an Explore subagent. Summarised each phase with the file / line where it lives and what it currently prints. Proposed names and asked the user to confirm granularity, naming (`Schema · prepare` vs `DDL (before)`), httpx noise suppression, nested-bar verbosity, and phase-header format — five open questions before sketching any UI.

### User

> When testing locally I am getting now this error: [screenshot showing:]
>
> ```
> Error: GET https://raw.githubusercontent.com/metabrainz/musicbrainz-server/2082249951e589f3ff0a42d76c6ffc4412b2d1b1/admin/sql/Extensions.sql failed: [Errno 9] Bad file descriptor
> ```
>
> (with the `Download mbdump.tar.bz2` progress bar shown twice in the terminal output)

### Assistant

Entered plan mode on the new error rather than continuing the progress-polish conversation. Launched an Explore subagent to map the call chain from download end to first `github.fetch`, audit httpx client lifecycle, check Rich `Live` / progress interactions, and review the most recent commit (`a713d0a`) which touches subprocess fd management.

The agent's hypothesis blamed `a713d0a`'s pbzip2 stderr drain thread. Read the agent's own summary carefully and rejected it: the agent acknowledged that `import_archive()` doesn't run until after `run_pre_import()` fails, so the pbzip2 subprocess isn't even spawned yet by the time the EBADF fires. Verified directly by reading `cli.py:run` (the loop sequence), `schema/orchestrator.py::run_pre_import()`, and `importer/archive.py`.

Read `sql/github.py::fetch`, `mirror/client.py::http_client`, `progress.py::ProgressManager`, `logging.py::get_console/configure`, `mirror/download.py::download_archive`, `schema/orchestrator.py`, `schema/psql.py`, `schema/extensions.py::preflight`, `db.py::connect`, `cli.py::_handle_errors`, and `errors.py`. Confirmed that between the end of the download and the first `github.fetch`, nothing opens subprocesses or closes fds; only psycopg queries on the already-open connection and the Rich `Progress` singleton `stop()` / `start()` cycle happen. Also noted the `Download …` bar rendering twice is a real cosmetic bug caused by `ProgressManager` being a module-level singleton with `transient=False` — the second `progress_session()` starts a new Rich `Live` but reuses the task list, so the completed first-session task re-renders on top.

Flagged that without the actual traceback, every candidate root cause is a guess (httpx socket open, SSL context, Rich `Live`, psycopg, stdio). The `_handle_errors` wrapper in `cli.py:326-335` calls `Console.print(f"[bold red]Error:[/] {exc}")` and exits — it throws away the traceback, so even at `-v` the user sees one line.

Asked the user two clarifying questions via `AskUserQuestion`:

1. **Debug strategy** — expose traceback first vs. guess-and-fix with retries vs. both. The user chose "Expose the traceback first, then fix".
2. **Cosmetic progress-bar fix** — include in this plan vs. defer. The user chose "Include it in this plan".

Wrote the plan to `/Users/rafa/.claude/plans/when-testing-locally-i-transient-parasol.md` with three parts:

1. Extend `_handle_errors`: when root logger level ≤ `DEBUG`, also call `console.print_exception(show_locals=False)` after the `Error:` line. Read the level via `logging.getLogger().getEffectiveLevel()` rather than re-plumbing Typer's `verbose` flag.
2. Add `ProgressManager.clear_tasks()` and call it from `progress_session()`'s `finally` after `stop()`, so the next session's fresh `Live` doesn't re-render prior tasks.
3. Out of scope: the targeted EBADF fix itself, because it depends on what the traceback reveals.

Called `ExitPlanMode` with two allowed prompts (`run pytest`, `run the CLI end-to-end for verification`).

### User

(User approved the plan via the plan-mode UI.)

## Decision log

- **Chose "expose traceback first" over guess-and-fix with retries.** Retries would have masked whatever Rich / httpx / OS interaction produced EBADF and carried dead complexity forward. One round-trip to get the traceback was cheap; writing the wrong fix twice would have cost much more.
- **Included the cosmetic progress-bar fix in this plan** at the user's request, on the premise that the singleton-re-entry pattern was visible in the same screenshots and was a real bug independent of the EBADF.
- **Did not plan a targeted EBADF fix yet.** Every candidate (httpx client lifecycle, Rich `Live`, psycopg socket fd numbers, SSL context, ssl retry+stale-fd on multi-address DNS) was a hypothesis without evidence. The plan explicitly punted to a follow-up PR.
- **Re-used `get_console()` and `logging.getLogger().getEffectiveLevel()`** rather than threading a `verbose` kwarg through `_handle_errors` — the context manager has no access to the Typer flags anyway, and the root logger's level is already the source of truth.
- **Kept `sys.exit(exc.exit_code)` untouched.** The behaviour of exit codes is part of the CLI contract; the change is additive (more output on `-v`), not a reshape of error handling.
