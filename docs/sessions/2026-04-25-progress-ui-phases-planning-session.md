# Planning session — Polish CLI progress UI (phase model + visual surface)

**Date:** 2026-04-25

**Session ID:** c282e150-9312-4076-9111-3e1b3b898bef

## Summary

The user opened the session by sharing a screenshot of a real `run` transcript (the 2026-04-23 first-successful-import scenario) and asking to polish the user-facing progress UI. Instead of jumping into UI tweaks, the conversation started by **defining the overall phases of the pipeline** as the foundation for any subsequent visual work. After mapping the codebase via an Explore subagent, the assistant proposed three discrete decisions for the user (phase granularity, plan scope, httpx noise), and the user picked: 5 top-level phases, full polish pass in one plan, and gate httpx INFO behind `-v`. The plan was written to `docs/plans/2026-04-25-progress-ui-phases.md` and approved via `ExitPlanMode`.

## Detailed conversation

### User

> Let's focus on polishing the CLI progress UI. This is a screenshot of the progress: [Image] There are INFO log entries and progress entries. We want to polish the user feedback.
> Let's start by defining the overall phases.

(Screenshot shows: rapid-fire `INFO HTTP Request: GET …` lines from httpx during phase 0/1, alternating `INFO Running admin/sql/X.sql` + `INFO admin/sql/X.sql finished in N.Ns` pairs through phase 3, then two progress bars at the bottom: an indeterminate `Import mbdump.tar.bz2  0/?  0/? bytes  ?  0:00:51` and an active `COPY musicbrainz.l_artist_recording  ████  902.8/1226.0 GiB  66 MB/s`.)

### Assistant

Spawned a single Explore subagent with a thorough brief asking it to map: top-level CLI entry points, the full import pipeline / orchestration with file paths and per-step logging behaviour, the logging + progress bar infrastructure, the `-v` flag wiring, and AGENTS.md / docs conventions.

Agent reported back a comprehensive map. Key findings:
- CLI is Typer-based at `src/musicbrainz_database_setup/cli.py`. End-to-end orchestrator is `cli.run()` (lines 248–277) which calls, in order: ref resolution → mirror dump-dir resolve → checksum fetch → archive download loop → DB connect → `Orchestrator.run_pre_import()` → archive import loop → `Orchestrator.run_post_import()`.
- Logging uses stdlib `logging` + `RichHandler` (rich.logging) at `src/musicbrainz_database_setup/logging.py`. `-v` sets root to DEBUG; default INFO; `--quiet` WARNING. No filters are applied to third-party loggers — `httpx` therefore pours its per-request INFO chatter directly into the screen.
- Progress is one shared `rich.progress.Progress` singleton at `src/musicbrainz_database_setup/progress.py` — `ProgressManager.instance()` — with download / spinner / copy tasks all sharing it. `transient=False` in the constructor, but the existing code already calls `pm.remove_task(...)` in `finally` blocks, so spinners (e.g. `psql Extensions.sql`) already vanish on completion.
- `cli.run()` opens TWO separate `progress_session()` blocks (downloads, then schema+import) — that means the Live table tears down + restarts between phases 2 and 3, which would interrupt any phase banner painted in between.
- Per-SQL-file output today is `INFO Running X` (orchestrator.py:114) + `INFO X finished in 0.1s` (orchestrator.py:122) + a transient `psql X.sql` spinner — three artefacts per file.
- Recent commit `ccbe98d` (the `-v` traceback work) showed the team's pattern: a small targeted change with a regression test and full doc treatment per AGENTS.md.

Read the key files (`cli.py`, `progress.py`, `schema/orchestrator.py`, `logging.py`, `importer/copy.py`, `schema/psql.py`, `AGENTS.md`) directly to ground the planned edits.

### Assistant

Asked the user three clarifying questions via `AskUserQuestion`, each with a previewable option to make the trade-offs concrete:

1. **Granularity of a phase.** Three options: 5 top-level phases (Mirror/Download/Schema-pre/Import/Schema-post — sub-steps shown via existing progress tasks), per-file granularity (15+ phases for core), or 5 top-level + structured "3.2 CreateCollations.sql" sub-step labels.
2. **Scope of this plan.** Phase model only (deferring visual polish), phase model + minimal UI (banner only), or full polish pass in one plan (banners + log noise reduction + visual grouping).
3. **httpx noise treatment.** Quiet at default verbosity (DEBUG-gated under `-v`), leave as-is, or always-quiet.

### User

Selected: **5 top-level phases**, **Full polish pass in one plan**, **Quiet httpx at default verbosity**.

### Assistant

Wrote the plan to `/Users/rafa/.claude/plans/let-s-focus-on-polishing-swirling-pearl.md` covering:

- The five-phase model: Mirror, Download, Schema (pre), Import, Schema (post). Sub-steps (individual SQL files, individual COPY tables) are explicitly *not* phases.
- A new `src/musicbrainz_database_setup/ui/phases.py` module with `RunPhase` StrEnum, `PHASE_ORDER` tuple, and a `phase_section` context manager that emits `Console.rule("Phase N/5 · <label>", style="bold cyan")` on entry and `INFO ✓ <label> · <elapsed>` on success. No footer on exception (the banner already in scrollback identifies the failing phase).
- Wiring `phase_section` into `cli.run()` and the standalone subcommands (`download`, `schema create`, `import`). Collapse the two `progress_session()` blocks in `run()` into one outer block so the Live table stays alive across phases.
- `httpx` + `httpcore` lifted in lockstep: WARNING by default, DEBUG under `-v`. The `--log-file` handler (DEBUG, file) keeps the full diagnostic trace for post-mortem.
- Compact per-SQL-file output: drop the `Running X` log entirely (the spinner already shows that); rewrite the completion log from `X finished in 0.1s` to `✓ X (0.1s)` so it visually pairs with the phase footer.
- Replace the indeterminate `Import mbdump.tar.bz2  0/?` parent task with a `INFO Importing X` header + a `INFO ✓ Imported X · N tables · M:SS` footer; per-table COPY bars stay because their `member.size` total is known.
- File list, doc list per AGENTS.md (plan + feature + two session transcripts + CHANGELOG entry + README note), and a verification recipe covering default vs `-v` runs + idempotency re-run + lint/type/tests.

Called `ExitPlanMode` to request approval.

### User

Approved the plan via the plan-mode UI.
