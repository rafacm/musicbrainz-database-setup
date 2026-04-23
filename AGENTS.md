# AGENTS.md

Guidance for AI coding assistants (Claude Code, etc.) working on this repository — architecture, code conventions, and workflow rules. Claude Code loads this file via `CLAUDE.md`, which just points here.

## What this project does

Python CLI (`musicbrainz-database-setup`) that points at an existing PostgreSQL 16+ instance and performs a full, one-shot MusicBrainz setup: downloads the `.tar.bz2` dump archives from the MetaBrainz mirror, creates the MusicBrainz schema by fetching `admin/sql/*.sql` from `metabrainz/musicbrainz-server` at a configurable git ref, and streams the TSVs inside the archives directly into `COPY FROM STDIN`.

Replication packets, JSON dumps, search-server integration, and any Docker-compose wrapper are explicit non-goals for v1.

## Build and dev commands

```bash
uv sync                                     # install deps + create .venv
uv run musicbrainz-database-setup --help          # smoke-test the CLI
uv run pytest                               # unit + integration
uv run pytest tests/unit/test_manifest.py   # single file
uv run ruff check src tests                 # lint
uv run mypy src                             # type-check
```

The CLI entrypoint is declared in `pyproject.toml` under `[project.scripts]` and resolves to `musicbrainz_database_setup.cli:app`.

## Architecture: the end-to-end pipeline

`cli.run` is the orchestrator. It calls, in order:

1. **Mirror client** (`mirror/`): resolves `--latest`/`--date` to a `DumpDirectory`, fetches `SHA256SUMS`, downloads each archive with a resumable `Range:`-based loop (`mirror/download.py`). All downloads write to `<name>.part` and only rename to the final name after checksum verify.
2. **Schema orchestrator** (`schema/orchestrator.py`): resolves the SQL git ref to a commit SHA via the GitHub API, then runs phases from `sql/manifest.py`. Pre-import phases are `Extensions`, `CreateCollations`, `CreateSearchConfiguration`, `CreateTypes`, `CreateTables` (core + per-module). Post-import phases are `CreatePrimaryKeys`, `CreateFunctions`, `CreateIndexes`, `CreateFKConstraints`, `CreateConstraints`, `SetSequences`, `CreateViews`, `CreateTriggers`. Each SQL file runs in its own transaction; completed phases are recorded in `musicbrainz_database_setup.applied_phases` so reruns are idempotent.
3. **Importer** (`importer/copy.py`): opens each archive with `tarfile.open(mode="r|bz2")` — pure streaming, no seeks, no disk extraction. For each `mbdump/<table>` member, runs `COPY <schema>.<table> FROM STDIN` via psycopg3's `cursor.copy()`, piping the tar member straight in. One transaction per archive. `ProgressManager` is the single shared `rich.progress.Progress` instance used by both the downloader and the COPY loop so nested bars render coherently.

The phase order mirrors upstream `admin/InitDb.pl`. If you change the order, check `InitDb.pl` for the authoritative reference — the official Perl scripts are the ground truth.

## Key conventions

- **Phase and archive bookkeeping both live in the `musicbrainz_database_setup` schema in the target DB** (`applied_phases`, `imported_archives`). Don't rename these without updating both `schema/orchestrator.py` and `importer/copy.py`.
- **SQL files are cached on disk keyed by the resolved commit SHA**, not by the ref the user typed. This means `master` invalidates automatically on the next commit. Cache lives under `${XDG_CACHE_HOME}/musicbrainz-database-setup/sql/<sha>/`.
- **Archives stream from `.part` → final name** only after SHA verification. Never read partial archives — always use the `dl.download_archive` return value.
- **Errors subclass `MBSetupError`** with a fixed `exit_code` attribute. The CLI's `_handle_errors` context manager translates them to `sys.exit(code)`; tests should `pytest.raises(SpecificError)`.
- **One `ProgressManager.instance()`** per process. Nested tasks are fine; don't instantiate a second `rich.progress.Progress` anywhere.
- **Module names on the CLI are hyphenated** (`cover-art`, not `cover_art`). The mapping to schemas and archive filenames lives in `sql/manifest.py` — one source of truth.

## Tricky bits

- `tarfile.open(mode="r|bz2")` is **streaming only**. `extractfile(info)` returns a file-like that's valid only until the next `next()` call. `iter_mbdump_members` yields these one at a time; callers MUST fully consume each member before advancing.
- `admin/sql/CreateCollations.sql` is pure ICU (`CREATE COLLATION ... provider = icu`) — no custom C extension. `admin/sql/Extensions.sql` defines `musicbrainz_unaccent` as a SQL function wrapping the stock `unaccent()`. `schema/extensions.preflight()` therefore only checks that `cube`/`earthdistance`/`unaccent` are available and that the server was built with ICU (via a `pg_collation` probe). Every official `postgres:*` image since PG 16 qualifies; no custom Dockerfile is required.
- `admin/sql/*.sql` files are psql-flavoured, not raw SQL: each starts with `\set ON_ERROR_STOP 1` and wraps its body in `BEGIN;/COMMIT;`. `schema/orchestrator._run_file` therefore shells out to `psql -f <file>` (matching `admin/InitDb.pl`) rather than trying to execute them through psycopg3. `schema/psql.py` builds the `psql` env from `conn.info` (host/port/user/dbname/password → PG* env vars) so credentials never reach the process-list. This makes `psql` a client-machine prerequisite — pre-flighted by `ensure_psql_available()`.
- `schema/psql.py` also sets `PGOPTIONS=-c search_path=musicbrainz,public -c client_min_messages=WARNING` on every psql invocation, mirroring upstream `admin/InitDb.pl`. The `search_path` is load-bearing: `CreateTables.sql` references `COLLATE musicbrainz` without schema qualification, so the `musicbrainz` schema must be on the search path for the collation lookup to succeed. The `client_min_messages=WARNING` suppresses NOTICE chatter (e.g. "using standard form 'und-u-kf-lower-kn'" when ICU normalises the locale) without hiding real warnings.
- Bulk session tuning (`SET LOCAL synchronous_commit=off`, etc.) is per-transaction. `db.bulk_session()` is a context manager — use it around the COPY loop, not at connect time.
- When adding a new module, update all four of: `MODULE_SUBDIR`, `MODULE_SCHEMA`, `MODULE_ARCHIVE` in `sql/manifest.py`, and `ALL_MODULES` in `config.py`.

## Out of scope for v1 (don't add)

- Replication-packet ingestion (`LATEST-replication`, hourly `replication-*.tar.bz2`).
- JSON dumps (`mbdump-json.tar.bz2` / `admin/sql/json_dump/`).
- Search-server setup (no Solr, no `CreateSearchIndexes.sql`).
- MB-Server / web UI bring-up.
- Multi-tenant or multi-DB-per-run support.
- Windows support.

---

# Branching

Before beginning any new work, always:
1. Verify we are on the `main` branch (`git branch --show-current`) and switch to it if not
2. Pull latest changes (`git pull --rebase`)
3. If there are any issues with steps 1–2 above, stop and ask for guidance before proceeding.

All new features and fixes must be implemented in a dedicated branch off `main`. Never commit directly to `main`. Use a descriptive branch name (e.g., `feature/replication-packets`, `fix/copy-session-leak`). Once the work is complete, open a pull request to merge back into `main`.

When creating PRs, use the rebase strategy. Squash and merge-commit strategies are not allowed on this repository.

---

# Documentation

### Planning phase

When a plan is accepted, save it to `docs/plans/`, one Markdown file per plan, with a `YYYY-MM-DD-` date prefix (e.g., `2026-04-22-replication-packets.md`).

Save the planning session transcript to `docs/sessions/`, with a `YYYY-MM-DD-` date prefix and a filename ending in `-planning-session.md` (e.g., `2026-04-22-replication-packets-planning-session.md`). Each transcript must include:

- **Session ID** — the actual Claude Code session UUID (e.g., `a150a5a3-218f-44b4-a02b-cf90912619d7`), after the `**Date:**` line. Do not use placeholders like "current session" or worktree names — retrieve the real UUID. Use `unavailable` only when the UUID cannot be recovered from session logs.
- **Summary** — a short `## Summary` describing what was planned.
- **Detailed conversation** — record the conversation as a sequence of `### User` and `### Assistant` sections. User messages must be verbatim, unedited text — copy the exact messages. Assistant sections may summarize tool calls, code changes, and internal reasoning into concise prose (since the raw output is tool invocations, not conversational text), but must capture what was done, what was explored, what alternatives were considered, and why a particular approach was chosen.

### Implementation phase

Feature documentation lives in `docs/features/`, one Markdown file per feature or significant change, with a `YYYY-MM-DD-` date prefix matching the plan file (e.g., `2026-04-22-replication-packets.md`). Each document should include:

- **Problem** — what was wrong or what need the feature addresses.
- **Changes** — what was modified, with enough detail that a reader can understand the approach without reading the diff.
- **Key parameters** — any tunable constants, their values, and why those values were chosen.
- **Verification** — how to test the change end-to-end (commands to run + expected behaviour; target PostgreSQL version and fixture data when the change is integration-level).
- **Files modified** — list of touched files with a one-line summary of each change.

Save the implementation session transcript to `docs/sessions/`, with a `YYYY-MM-DD-` date prefix and a filename ending in `-implementation-session.md` (e.g., `2026-04-22-replication-packets-implementation-session.md`). Same format as the planning session (session ID, summary, verbatim conversation with reasoning steps). The implementation transcript must include all interactions up to and including PR review feedback and any follow-up changes made after the PR is created.

Every doc file must start with a `# Title` on the very first line. Metadata lines go immediately after the title, before any `## Section`: first `**Date:** YYYY-MM-DD` (all doc types), then `**Session ID:**` (session transcripts only). Never place metadata above the title. Separate each metadata line with a blank line so they render as distinct paragraphs in Markdown (e.g., a blank line between `**Date:**` and `**Session ID:**`).

Keep prose concise. Prefer tables and lists over long paragraphs. Use code blocks for CLI commands and signal-flow diagrams.

### Changelog & env vars

Whenever a `MUSICBRAINZ_DATABASE_SETUP_*` environment variable is added, changed, or removed, update the configuration table in `README.md` and the corresponding field on the `Settings` class in `src/musicbrainz_database_setup/config.py`.

`CHANGELOG.md` follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format, using dates (`## YYYY-MM-DD`) as section headers instead of version numbers. Under each date, group entries by category (`### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`). Each entry includes a short description and links to the plan document, the feature document, and both session transcripts. Newest dates first; add to an existing date section if one already exists for today.

The commit for a given feature MUST contain the plan, the feature documentation, and both session transcripts (planning and implementation).

---

# PR Creation

When creating PRs, ensure the PR includes: plan document, feature doc, session transcripts (planning + implementation), and changelog entry. Review the Documentation section above for full requirements before creating the PR.

---

# GitHub API (gh)

When using `gh api` to interact with GitHub:

- **Shell escaping:** Always wrap request bodies containing backticks or special characters in a `$(cat <<'EOF' ... EOF)` heredoc. Bare backticks in `-f body="..."` will be interpreted by zsh as command substitution.
- **Replying to PR review comments:** POST to the pull's comments endpoint with `in_reply_to`:
  ```bash
  gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments \
    -f body="reply text" \
    -F in_reply_to=COMMENT_ID
  ```
  There is no `/replies` sub-endpoint on individual comments — that returns 404.
- **Fetching PR review comments:** Use `gh api repos/OWNER/REPO/pulls/PR_NUMBER/comments` (not `/reviews`).
- **Fetching PR general comments:** Use `gh api repos/OWNER/REPO/issues/PR_NUMBER/comments` (PRs are issues).
