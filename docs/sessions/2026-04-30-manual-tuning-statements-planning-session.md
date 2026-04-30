# Planning session — Document manual `psql` ALTER SYSTEM tuning as the recommended speedup path

**Date:** 2026-04-30

**Session ID:** 98e4f5a7-1d2c-4cc8-83d5-68150ef766f5

## Summary

The user opened the session pointing at [issue #13](https://github.com/rafacm/musicbrainz-database-setup/issues/13), which proposed a `--auto-tune` CLI flag that would have the tool itself `ALTER SYSTEM SET …` before the import and `ALTER SYSTEM RESET …` afterward — preserving the one-shot `uvx --from git+… run --auto-tune` story without forcing users to recreate their Postgres container with `-c` flags. The assistant proposed an initial plan that mirrored the issue's three-option `shared_buffers` design (skip-by-default plus optional `--postgres-container` add-on for Docker users) and asked for confirmation. The user invoked `/grill-me`, and the conversation walked the design tree question by question.

The grill collapsed the design under its own weight. Each branch the assistant raised — privilege preflight method, lifecycle bracketing, revert-failure handling, apply atomicity, container-restart timing — was answered consistently in the direction of "less code, fewer touch points, leave the user's Postgres alone." On Q11 (apply atomicity) the user said "this is getting complicated" and proposed the simpler answer: drop the flag entirely; document two `psql` blocks (apply, revert) in `docs/README.md` and let users run them.

The final plan: documentation-only change. Replace the existing `docker run … -c shared_buffers=2GB …` block in `docs/README.md` with two `psql` ALTER SYSTEM blocks bracketing the `run` command (four SIGHUP-reloadable knobs, no `shared_buffers`, no Postgres restart). Update the README quick-start 💡 callout to point at the new path. Rewrite the ⚠️ Memory-sizing callout to anchor on `maintenance_work_mem` rather than `shared_buffers`. Close issue #13 with a comment summarizing the conversation. Plan saved to `docs/plans/2026-04-30-manual-tuning-statements.md`.

## Detailed conversation

### User

> Let's work on this issue https://github.com/rafacm/musicbrainz-database-setup/issues/13

### Assistant

Read issue #13 with `gh issue view 13`. The issue lays out the friction (committed `docker-compose.yml`, shared instances, managed cloud DBs make the documented `-c` flag tuning a "take it or leave it" choice), proposes a `--auto-tune` flag with apply-before / revert-after lifecycle, walks three options for handling `shared_buffers` (postmaster-only, can't be `pg_reload_conf()`'d): skip by default, print-and-wait, or optional `--postgres-container` Docker integration, and lists failure modes (mid-import crash, missing privilege, server-wide effect across other DBs).

Read the project layout — `AGENTS.md` for the workflow rules (branch off `main`, plan to `docs/plans/`, planning + implementation session transcripts to `docs/sessions/`, feature doc to `docs/features/`, CHANGELOG entry, gh comment style), `cli.py` for the `run` command structure, `db.py` for connection handling, `errors.py` for the error class hierarchy, `config.py` for the env-var pattern, the existing "Server-side tuning" section in `docs/README.md`, and the `2026-04-24-faster-import.md` plan to understand which phases the tuning actually accelerates (mostly the post-import DDL — `CreateIndexes`, `CreateFKConstraints`, `CreateConstraints`).

Wrote an initial plan: new `tuning.py` module (apply/revert + privilege preflight + Docker container restart helper), `--auto-tune` and `--postgres-container` flags on `run` only, marker file at `${XDG_CACHE_HOME}/musicbrainz-database-setup/tuning-applied.json` for crash recovery, lifecycle bracketed in `try/finally`, README docs updated. Asked three open questions: (1) `shared_buffers` default with `--postgres-container` — agree to include it? (2) Without a container, do we expose the print-and-wait prompt option from the issue? (3) Scope — `--auto-tune` only on `run`, not standalone `schema create` / `import`?

### User

> /grill-me

### Assistant

Switched into grill-me mode. Walked the design tree one question at a time, providing a recommended answer for each.

**Q1 — Where does `--auto-tune` live in the CLI?** Three options: A) `run` only; B) `run`, `schema create`, and `import` per-subcommand; C) top-level callback flag. Recommended A — the lifecycle is a single coherent transaction the `run` command owns end-to-end; standalone subcommands are "I'm composing pieces myself" mode where the user can apply tuning manually.

### User

> We want this optimization to apply to the main command we show in the README
> uvx --from git+https://github.com/rafacm/musicbrainz-database-setup \
>   musicbrainz-database-setup run \
>   --db postgresql://postgres:postgres@localhost:5432/postgres \
>   --modules core \
>   --latest
> Just by adding --auto-tune at the end it should be possible to get the improvements.

### Assistant

Confirmed A. The user's framing also confirmed the flag should be opt-in (off by default), matching the issue.

**Q2 — `shared_buffers` and the `--postgres-container` flag.** Three sub-questions: (Q2a) when `--auto-tune` is given alone (no container flag), do we still `ALTER SYSTEM SET shared_buffers` knowing the value won't take effect without a restart? Recommended **no** — leaves a latent surprise next time the user restarts Postgres themselves. (Q2b) `--postgres-container` without `--auto-tune` — error, implicit-enable, or warn-and-ignore? Recommended error. (Q2c) Container restart timing — restart once after applying all settings; restart again on revert; abort on docker failure (don't silently degrade).

### User

> Let's not complicate this too much. The tool is focused on people who already have their own postgres database up and running so we want to touch it as less as possible.

### Assistant

Major scope reduction. Reflected back: drop `--postgres-container` entirely; `--auto-tune` does only the four SIGHUP-reloadable knobs (`max_wal_size`, `checkpoint_timeout`, `effective_io_concurrency`, `random_page_cost`); no `shared_buffers`; no container restart; no docker integration; never touch the postmaster.

**Q3 — Privilege handling when `ALTER SYSTEM` fails.** Two options: A) hard fail with a clear "drop `--auto-tune` or use a superuser" message; B) warn and continue with an unaccelerated import. Recommended A — silent skip (B) violates the "user asked for this" contract and a hidden warning would make the slow import look mysterious.

### User

> If the postgres instance needs a restart then we should pass on that.

### Assistant

User reinforced the Q2 decision (zero restarts). Re-asked Q3.

### User

> Yes, agreed with A

### Assistant

A confirmed.

**Q4 — Crash-recovery marker file.** A) implement the marker (write at apply, remove at revert, detect-and-prompt on next `run`); B) skip the marker — `try/finally` plus an `atexit` handler covers everything except hard crashes (`kill -9`, OOM), and the consequence of a leaked apply is just "Postgres has slightly larger WAL/checkpoint settings until the next restart or manual reset" — recoverable, not catastrophic. Recommended B.

### User

> b

### Assistant

B confirmed.

**Q5 — Setting values: hardcoded or configurable?** A) hardcoded constants; B) per-knob CLI overrides; C) config-file escape hatch. Recommended A — values match the existing docs, and the whole point of the flag is "no more thinking required."

### User

> yes

### Assistant

A confirmed.

**Q6 — README quick-start prominence.** A) add `--auto-tune` to the headline command; B) keep headline as-is, replace the 💡 callout to advertise the flag; C) both. Recommended B — headline stays minimum-viable (no privilege assumption); callout is the natural advertising slot.

### User

> B

### Assistant

B confirmed.

**Q7 — Apply / revert timing within `run`.** A) preflight + apply at the very top, revert in `finally` (apply happens before download); B) preflight at top, apply just before `connect(db)` for import (tighter window, two short-lived connections). Recommended A as the simpler bracket.

### User

> I don't understand the options. We should enable tuning in a tighter window, or? If we fail to download the dump we do not need to apply the tuning statements.

### Assistant

User pushed back — B is better. If download fails we shouldn't have touched `postgresql.auto.conf` at all. Reflected back the corrected flow: privilege preflight at top → resolve mirror + download → apply → `try` (connect + schema-pre + import + schema-post) `finally` revert.

**Q8 — UI: phases or log lines?** A) two new `RunPhase` entries (`TUNING_APPLY`, `TUNING_REVERT`) with phase headings; B) plain `log.info` lines (the four ALTER SYSTEMs are <100 ms total — phase headings would be visual overkill). Recommended B.

### User

> Let's go for A to make it 100% explicit what we are doing.

### Assistant

A confirmed — two new phases.

**Q9 — Privilege preflight method.** A) `is_superuser` (simple but rejects legitimate `pg_alter_system` users on PG 16+); B) `pg_has_role(current_user, 'pg_alter_system', 'MEMBER') OR is_superuser`; C) capability probe (run a no-op `ALTER SYSTEM` in a try/except). Recommended B — accurate, single round-trip, no side effects, and PG 16+ is our minimum.

### User

> yes

### Assistant

B confirmed.

**Q10 — Revert failure.** A) warn + recovery one-liner, exit code reflects import outcome only; B) error + recovery one-liner, exit non-zero even if import succeeded; C) retry with backoff. Recommended B — silent success on cleanup failure violates the contract; the user needs to know.

### User

> yes

### Assistant

B confirmed.

**Q11 — Apply atomicity.** ALTER SYSTEM is implicitly auto-commit (writes to `postgresql.auto.conf` per statement, no transactional rollback). What if statement 2 of 4 fails? A) best-effort cleanup (RESET the ones that succeeded); B) hard abort with recovery message; C) don't even handle it — the `finally` revert path will RESET all four anyway, and RESET on a setting that was never set is a no-op. Recommended C — with hardcoded values, the only realistic failure is a server-side disaster, where the user has bigger problems.

### User

> This is getting complicated. Could we do this by offering two psql commands for before and after that can be run from the command-line in case they want to improve the performance and we document them in the doc/README?

### Assistant

The pivot point. Reflected the simpler proposal back as a complete redesign: zero code changes, documentation only. Add an apply `psql` block and a revert `psql` block to `docs/README.md`'s "Server-side tuning (optional)" section, bracketing the `run` command. Drop the `--auto-tune` flag, the `tuning.py` module, the privilege preflight, the lifecycle code, the marker file, the revert-failure handling, the apply atomicity reasoning, the new phases. The README's headline command stays single-line; the 💡 callout still points at `docs/README.md` with the new content.

Asked Q12: **(Q12a)** issue disposition — close with a comment, or keep open and rename? Recommended close — the original framing was "preserve the one-shot story", and three commands (psql apply + run + psql revert) doesn't preserve that story; honest answer is to punt on the original ask and document the alternative. **(Q12b)** does the new psql block live next to the existing `-c` flags block, or replace it? Recommended live-next-to.

### User

> Q12b: document our conversation in the issue and the resulting decision.
> Q12b: replace the -c flags. But we still need to document what each of the statements does.

### Assistant

User numbered both responses "Q12b" but the first answers Q12a (post a comment summarizing the conversation, then close). The second replaces the `-c` flag block entirely (not side-by-side), keeping per-setting rationale.

That meant `shared_buffers=2GB` drops out of the documented path entirely, which orphans the existing ⚠️ "Memory sizing" callout (it currently anchors on `shared_buffers=2GB`).

**Q13 — Memory-sizing callout.** A) drop entirely; B) rewrite around `maintenance_work_mem` × `1 + max_parallel_maintenance_workers` workers (~5 GB peak during CREATE INDEX); C) keep a short note pointing at the `-c shared_buffers=2GB` startup flag for power users. Recommended **B + a one-line nod to C**.

**Q14 — Branch and deliverables.** Branch name `docs/manual-tuning-statements`; full project-rule-compliant deliverable set (plan, planning session, implementation session, feature doc, CHANGELOG entry, docs/README.md edits, issue comment + close).

### User

> Q13: let's go with your recommendation.
> Q14: a) ok b) yes

### Assistant

All decisions locked in. Wrote a final summary covering the locked-in design and asked for go-ahead.

### User

> yes

### Assistant

Plan accepted. Created the `docs/manual-tuning-statements` branch off `main`, wrote the plan to `docs/plans/2026-04-30-manual-tuning-statements.md`, then started executing the documentation edits.
