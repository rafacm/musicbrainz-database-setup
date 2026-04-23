# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), using dates (`## YYYY-MM-DD`) as section headers instead of version numbers.

## 2026-04-22

### Added

- Initial implementation of the `musicbrainz-database-setup` CLI — downloads MusicBrainz dump archives, creates the schema (by fetching `admin/sql/*.sql` from `metabrainz/musicbrainz-server` at a configurable git ref), and streams the TSVs into `COPY FROM STDIN`. Plan: [`docs/plans/2026-04-22-initial-implementation.md`](docs/plans/2026-04-22-initial-implementation.md). Feature doc: [`docs/features/2026-04-22-initial-implementation.md`](docs/features/2026-04-22-initial-implementation.md). Sessions: [planning](docs/sessions/2026-04-22-initial-implementation-planning-session.md), [implementation](docs/sessions/2026-04-22-initial-implementation-implementation-session.md).

### Changed

- Renamed `docs/PREREQUISITES.md` → `docs/README.md` and rewrote the "PostgreSQL server" section to lead with the Docker image shipped in `tests/docker/` (build, `docker run`, use the entrypoint-created `postgres` superuser, or optionally create a dedicated `mb` superuser). The manual "compile extensions on the PG host" instructions are preserved as a secondary "Pointing at a pre-existing PostgreSQL server" sub-section.

## 2026-04-23

### Removed

- Deleted `tests/docker/Dockerfile`. Upstream `musicbrainz-server` removed the `postgresql-extensions/` directory — `CreateCollations.sql` is now a plain ICU collation (`CREATE COLLATION ... provider = icu`) and `musicbrainz_unaccent` is a SQL function defined inline in `Extensions.sql`. No custom PG build is required; any official `postgres:*` image works (including `postgres:17-alpine`).
- Removed `REQUIRED_COLLATION_EXTENSIONS` from `schema/phases.py` and the matching preflight check in `schema/extensions.py`.

### Changed

- `schema/extensions.preflight()` now probes `pg_collation` for ICU support (via `collprovider = 'i'`) instead of looking for `musicbrainz_collate` / `musicbrainz_unaccent` extensions.
- Rewrote `docs/README.md` around vanilla `postgres:*` images — including an `image: postgres:17-alpine` snippet for projects that already have a docker-compose.yml. Added a note on managed Postgres (RDS, Cloud SQL).
- Renamed the project end-to-end from `musicbrainz-db-setup` → `musicbrainz-database-setup` for SEO and CLI/package/repo consistency. Affected: Python module (`musicbrainz_db_setup` → `musicbrainz_database_setup`), PyPI package, CLI entrypoint, env-var prefix (`MUSICBRAINZ_DB_SETUP_*` → `MUSICBRAINZ_DATABASE_SETUP_*`), bookkeeping PG schema (`musicbrainz_db_setup` → `musicbrainz_database_setup`), XDG cache paths, and the GitHub repo itself. Verbatim user messages from prior session transcripts were preserved.
- Rewrote the root `README.md`: direct opening paragraph stating what the tool is, a `Requirements` section that cites upstream sources (`Extensions.sql`, `CreateCollations.sql`, the `postgres` Docker image), a Quick start that boots `postgres:17-alpine` and imports the `core` module in three commands, a full `Modules` table with archive / target schema / contents / licence, and a `References` section linking to every primary source this tool is built on.

### Removed

- Deleted `docs/README.md`. Its content (PG requirements, docker-compose snippet, managed-PG note, disk sizing) folded into the root `README.md` where it belongs alongside the Quick start — one README is clearer than two for prerequisites.

### Added

- `LICENSE` file at the repo root (MIT, © 2026 Rafael Cordones). Matches the existing `pyproject.toml` declaration and brings this project in line with the rest of the MB tooling layer (`mbdata`, `mbslave`, `musicbrainz-docker` are all MIT). `pyproject.toml` now points at the file via `license = { file = "LICENSE" }`.
- New `Status` section in `README.md` with "What's already implemented" (bulleted summary of shipped functionality) and "What's coming" (`SCHEMA_SEQUENCE` cross-check, canary CI for upstream phase-file drift, pre-built GHCR runner image).

### Fixed

- Schema orchestrator failed on the very first SQL file with `syntax error at or near "\"` because the upstream `admin/sql/*.sql` files are psql-flavoured (start with `\set ON_ERROR_STOP 1`, wrap themselves in `BEGIN;/COMMIT;`) and we were handing them to psycopg3 directly. New `schema/psql.py` shells out to `psql -f <file>` using credentials extracted from the psycopg connection — matching what `admin/InitDb.pl` does upstream. `psql` is now a documented client-machine requirement and `schema.psql.ensure_psql_available()` pre-flights it. Dropped the now-redundant `schema.extensions.ensure_extensions()` since `Extensions.sql` does the same `CREATE EXTENSION IF NOT EXISTS` calls itself.
- `CreateTables.sql` failed at line 434 with `collation "musicbrainz" for encoding "UTF8" does not exist` because the file uses `COLLATE musicbrainz` unqualified, the collation lives in the `musicbrainz` schema, and our psql invocations started with the server-default `search_path` ("$user", public). `schema/psql.py` now sets `PGOPTIONS='-c search_path=musicbrainz,public -c client_min_messages=WARNING'` on every psql call — byte-for-byte what upstream `admin/InitDb.pl` does. The `client_min_messages=WARNING` also suppresses NOTICE chatter like `CreateCollations.sql`'s "using standard form 'und-u-kf-lower-kn'".
- The import phase aborted immediately with `can't change 'autocommit' now: connection in transaction status INTRANS`. `import_archive()` calls `already_imported()` (a `SELECT` probe on the bookkeeping table) right before entering `bulk_session()`, which left the connection in INTRANS. `bulk_session` then unconditionally assigned `conn.autocommit = False`, and psycopg3 refuses that assignment — even when the new value equals the current one — unless the connection is IDLE. `db.bulk_session()` now only flips the attribute when it actually needs to change, matching the psycopg3 contract.
