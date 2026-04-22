# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), using dates (`## YYYY-MM-DD`) as section headers instead of version numbers.

## 2026-04-22

### Added

- Initial implementation of the `musicbrainz-db-setup` CLI — downloads MusicBrainz dump archives, creates the schema (by fetching `admin/sql/*.sql` from `metabrainz/musicbrainz-server` at a configurable git ref), and streams the TSVs into `COPY FROM STDIN`. Plan: [`docs/plans/2026-04-22-initial-implementation.md`](docs/plans/2026-04-22-initial-implementation.md). Feature doc: [`docs/features/2026-04-22-initial-implementation.md`](docs/features/2026-04-22-initial-implementation.md). Sessions: [planning](docs/sessions/2026-04-22-initial-implementation-planning-session.md), [implementation](docs/sessions/2026-04-22-initial-implementation-implementation-session.md).

### Changed

- Renamed `docs/PREREQUISITES.md` → `docs/README.md` and rewrote the "PostgreSQL server" section to lead with the Docker image shipped in `tests/docker/` (build, `docker run`, use the entrypoint-created `postgres` superuser, or optionally create a dedicated `mb` superuser). The manual "compile extensions on the PG host" instructions are preserved as a secondary "Pointing at a pre-existing PostgreSQL server" sub-section.
