# Initial implementation plan

**Date:** 2026-04-22

## Context

Greenfield repository. Goal: a Python CLI (`musicbrainz-database-setup`) that, given a PostgreSQL connection, lists/selects a MusicBrainz dump on the MetaBrainz mirror, downloads the selected archives with progress bars and SHA256 verification, creates the MusicBrainz schema by fetching the upstream `admin/sql/*.sql` files at a pinned git ref, and streams the TSVs inside the archives directly into `COPY FROM STDIN` with per-table progress bars.

Today this process is scattered across the MusicBrainz wiki, `musicbrainz-server/admin/`, `mbslave`, and `musicbrainz-docker`. A single Python tool with a clean CLI consolidates it.

## Confirmed scope decisions

- Default dump = core (`mbdump.tar.bz2`); all other modules (derived, editor, edit, caa, eaa, stats, documentation, wikidocs, cdstubs) opt-in via `--modules`.
- One-shot full import only. Replication packets are out of scope for v1.
- Tool connects as a superuser-capable role and runs DDL itself (including `CREATE EXTENSION`). Operator pre-installs the custom C extensions (`musicbrainz_collate`, `musicbrainz_unaccent`).
- SQL files are fetched from `metabrainz/musicbrainz-server` on GitHub at a configurable git ref, disk-cached by resolved commit SHA.
- Dump selection: explicit `--date`/`--dump-dir`/`--latest` flag, otherwise interactive picker.
- Download and import both show `rich` progress bars.

## Library & tooling choices

- **Package manager: uv** — single binary, fast, handles Python install + lockfile + scripts.
- **Python: ≥3.11.**
- **CLI: Typer** — type-hint-driven wrapper over Click.
- **HTTP: httpx** — HTTP/2, Range support for resumable downloads.
- **DB driver: psycopg 3** with `copy()` API for server-side `COPY FROM STDIN`.
- **Progress: rich** (`rich.progress` with nested tasks).
- **Interactive picker: questionary.**
- **Config: pydantic-settings** (flags > env > `.env` > defaults).

## Package layout

```
musicbrainz-database-setup/
├── pyproject.toml
├── src/musicbrainz_database_setup/
│   ├── cli.py               # Typer app + subcommands
│   ├── config.py            # pydantic-settings
│   ├── logging.py, progress.py, db.py, errors.py, verify.py
│   ├── mirror/              # httpx client, index parser, SHA verify, resumable download
│   ├── sql/                 # GitHub fetch, SHA-keyed disk cache, per-module manifest
│   ├── schema/              # orchestrator, phases enum, extension preflight
│   └── importer/            # streaming tar, COPY FROM STDIN, table→schema manifest
├── tests/
│   ├── unit/                # offline fixtures
│   └── docker/Dockerfile    # PG 16 + musicbrainz_collate/unaccent for integration
└── docs/README.md
```

## CLI surface

- `musicbrainz-database-setup list-dumps [--limit N] [--mirror URL]`
- `musicbrainz-database-setup download [--date | --latest | --dump-dir] [--modules ...] [--verify/--no-verify]`
- `musicbrainz-database-setup schema create [--db URL] [--ref GITREF] [--modules ...] [--phase pre|post|all]`
- `musicbrainz-database-setup import [--db URL] [--dump-dir PATH] [--modules ...]`
- `musicbrainz-database-setup run [--db URL] [--modules ...] [--date | --latest] [--ref GITREF]` — end-to-end
- `musicbrainz-database-setup verify [--dump-dir PATH]`
- `musicbrainz-database-setup clean [--workdir DIR]`

## Schema phases (mirrors `admin/InitDb.pl`)

**Pre-import**: Extensions → CreateCollations → CreateSearchConfiguration → CreateTypes → CreateTables (core + per-module).

**COPY phase**: one transaction per archive; `bulk_session()` sets `synchronous_commit=off`, large work_mem; stream tar members into `COPY <schema>.<table> FROM STDIN`.

**Post-import**: CreatePrimaryKeys → CreateFunctions → CreateIndexes → CreateFKConstraints → CreateConstraints → SetSequences → CreateViews → CreateTriggers → VACUUM ANALYZE.

Bookkeeping: `musicbrainz_database_setup.applied_phases` and `musicbrainz_database_setup.imported_archives` tables make reruns idempotent.

## Error handling & exit codes

0 ok · 1 user error · 2 network · 3 checksum · 4 SQL/DDL · 5 COPY · 130 SIGINT. Errors subclass `MBSetupError` with a fixed `exit_code`.

## Non-goals for v1

No replication packets. No JSON dumps. No search server (Solr). No MB-Server web UI. No Docker-compose wrapper. No Windows. No schema migrations across SCHEMA_SEQUENCE versions.

## Verification

1. `uv sync && uv run musicbrainz-database-setup --help` prints the subcommand tree.
2. `uv run musicbrainz-database-setup list-dumps` hits the real mirror.
3. `uv run pytest -q` — unit tests (offline) pass.
4. `uv run ruff check src tests` — clean.
5. Integration path (post-PR): build `tests/docker/Dockerfile` as `musicbrainz-database-setup-test-pg:16`, `uv run musicbrainz-database-setup run --db postgresql://postgres:x@localhost/mb --modules core --latest`.
