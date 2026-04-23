# Initial implementation — planning session

**Date:** 2026-04-22

**Session ID:** 2b602587-6dc5-4c34-89cf-a23e1bf64feb

## Summary

Scoped a greenfield Python CLI for downloading MusicBrainz dump archives and importing them into an existing PostgreSQL instance. Settled on: uv + Python 3.12, Typer CLI, httpx, psycopg 3, rich progress bars, one-shot full import (no replication packets in v1), SQL files fetched at runtime from `metabrainz/musicbrainz-server` at a configurable git ref, SHA-keyed disk cache, and the phase order mirroring `admin/InitDb.pl`.

## Detailed conversation

### User

> Please analyze this codebase and create a CLAUDE.md file

### Assistant

Found the repository empty — no files, no commits, only an initialised `main` branch. Declined to fabricate a CLAUDE.md against a non-existent codebase and instead offered three paths (wait until code exists, describe the intended project, or a minimal stub).

### User

> I want to build a Python-based tool that can be pointed to a PostgreSQL instance and the tools will download the MusicBrainz database dumps, create the schema and import the dumps into the PostgreSQL database. Currently the information on how to do this is scattered among several scripts and pages: [wiki + github links]

### Assistant

Launched three parallel research agents (via WebFetch) covering: (a) the MetaBrainz mirror layout and dump archive inventory, (b) the `admin/sql/` SQL files and `InitDb.pl` phase order, (c) existing Python tooling (`mbslave`, `mbdata`, `musicbrainz-docker`). Findings: dumps live at `data.metabrainz.org/.../fullexport/<YYYYMMDD-HHMMSS>/` with `SHA256SUMS`; `InitDb.pl` runs Extensions → Collations → Types → Tables → (COPY) → PrimaryKeys → Functions → Indexes → FKs → Constraints → Sequences → Views → Triggers; required extensions `cube`, `earthdistance`, `unaccent`, plus custom `musicbrainz_collate`/`musicbrainz_unaccent` C extensions.

Presented four scope questions via AskUserQuestion.

### User

> The tool should default to core but it should be possible to also process/import the other dumps too.

### Assistant

Noted: default core, all other modules (`derived`, `editor`, `edit`, `cover-art`, `event-art`, `stats`, `documentation`, `wikidocs`, `cdstubs`) opt-in. Asked the remaining three.

### User

(answered via AskUserQuestion)
- Replication: one-shot full import only
- PG assumptions: tool runs DDL as superuser-capable role

### Assistant

> Let me ask what you want to clarify on the SQL source question.

### User

> Let's go for two. The tool should also allow to pass a specific dump or if none is passed then allow the user to select one from the ones available remotely. The tool should also show download progress of the dumps and also import progress bars into the database.

### Assistant

Confirmed: SQL files fetched from GitHub at a configurable git ref, plus interactive picker when no dump is specified, plus rich progress bars on both download and import. Launched a Plan agent to turn the scope into a concrete design. The Plan agent returned a ~1200-word design covering package layout, CLI surface, mirror client, SQL fetcher with SHA-keyed cache, schema phases, streaming importer, progress UI, error handling, configuration, testing, prerequisites, and v1 non-goals. Wrote the final plan to `/Users/rafa/.claude/plans/i-want-to-build-frolicking-aho.md`.

### User

> The tool will be called musicbrainz-db-setup

### Assistant

Renamed the CLI entrypoint, Python module (`musicbrainz_db_setup`), env-var prefix (`MUSICBRAINZ_DB_SETUP_`), Docker image tag, config file, log filename, and bookkeeping schema throughout the plan file. Exited plan mode.
