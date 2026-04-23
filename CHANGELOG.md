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
