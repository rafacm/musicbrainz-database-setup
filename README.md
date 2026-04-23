# musicbrainz-database-setup

`musicbrainz-database-setup` is a Python CLI that sets up a full MusicBrainz database in a PostgreSQL instance you control. It downloads the official dumps from the MetaBrainz mirror, creates the schema by running the upstream `admin/sql/*.sql` files against your database, and streams the TSVs inside the archives directly into `COPY FROM STDIN` — no disk extraction, with resumable downloads, SHA256 verification, and per-table progress bars.

The steps this tool automates are otherwise scattered across the [MusicBrainz wiki](https://wiki.musicbrainz.org/MusicBrainz_Database/Download), the `musicbrainz-server` [admin Perl scripts](https://github.com/metabrainz/musicbrainz-server/tree/master/admin), and the [`metabrainz/musicbrainz-docker`](https://github.com/metabrainz/musicbrainz-docker) stack. This project consolidates them into a single command you can point at any PostgreSQL connection.

## Requirements

PostgreSQL **16 or later** with:

- The **`cube`**, **`earthdistance`**, and **`unaccent`** extensions — declared in upstream [`admin/sql/Extensions.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/Extensions.sql). They ship with the `postgresql-contrib` package, which is bundled in every official [`postgres:*` Docker image](https://hub.docker.com/_/postgres).
- **ICU support** (server built with `--with-icu`). The MusicBrainz collation in [`admin/sql/CreateCollations.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/CreateCollations.sql) uses `provider = icu`. Every official `postgres:*` image since PG 16 qualifies.
- A role with **`SUPERUSER`** privileges so the tool can `CREATE EXTENSION`. The default `postgres` user created by the official image works.

The tool pre-flights `pg_available_extensions` and `pg_collation` at startup and aborts with an actionable message if anything is missing.

The **`psql` client** must be available on `$PATH` on the machine running the tool. The upstream `admin/sql/*.sql` files use psql meta-commands (`\set ON_ERROR_STOP 1`, etc.) and manage their own `BEGIN;/COMMIT;` — we shell out to `psql` for each file, mirroring `admin/InitDb.pl`'s own approach, rather than reimplementing that parsing in Python. Install it with `brew install libpq` (macOS), `apt install postgresql-client` (Debian/Ubuntu), `apk add postgresql-client` (Alpine), or the equivalent on your distro.

**Disk:** expect ~10–15 GB of downloads for `core`, ~30 GB for `core + derived`, and the live database grows to roughly 100–160 GB once indexes are built. More if `cover-art` or `event-art` are selected.

The tool also works against managed PostgreSQL (RDS, Cloud SQL, etc.) as long as the role you connect as can `CREATE EXTENSION` (on RDS that's `rds_superuser`; on Cloud SQL, `postgres`).

## Quick start

1. **Start a Postgres instance.** Any official `postgres:*` image works. `--name` is the Docker container name (for `docker exec` / `docker stop`); the database name used by the tool is `postgres`, the default created by the image's entrypoint.

    ```bash
    docker run -d --name musicbrainz-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17-alpine
    ```

2. **Install the CLI.**

    ```bash
    uv sync
    ```

3. **Download, create the schema, import, and finalise, end-to-end.** Connection string is `postgresql://<user>:<password>@<host>:<port>/<database>`.

    ```bash
    uv run musicbrainz-database-setup run --db postgresql://postgres:postgres@localhost:5432/postgres --modules core --latest
    ```

If neither `--latest` nor `--date YYYYMMDD-HHMMSS` is passed, `run` interactively prompts for a dump directory from the mirror.

## Modules

The MusicBrainz database is split across several `.tar.bz2` archives on the mirror. `--modules` (comma-separated) selects which to download and import. `core` is the default; the others are opt-in.

| Module | Archive | Target schema | Contents | Licence |
|---|---|---|---|---|
| `core` | `mbdump.tar.bz2` | `musicbrainz` | Artists, releases, recordings, works, labels, areas, places, events, series, instruments, URLs, genres. | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) |
| `derived` | `mbdump-derived.tar.bz2` | `musicbrainz` | Annotations, ratings, tags, search helpers. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `editor` | `mbdump-editor.tar.bz2` | `musicbrainz` | Editor accounts. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `edit` | `mbdump-edit.tar.bz2` | `musicbrainz` | Edit history. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `cover-art` | `mbdump-cover-art-archive.tar.bz2` | `cover_art_archive` | Cover Art Archive metadata. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `event-art` | `mbdump-event-art-archive.tar.bz2` | `event_art_archive` | Event Art Archive metadata. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `stats` | `mbdump-stats.tar.bz2` | `statistics` | Site statistics. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `documentation` | `mbdump-documentation.tar.bz2` | `documentation` | Wiki documentation for entities. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `wikidocs` | `mbdump-wikidocs.tar.bz2` | `wikidocs` | Stored wiki-docs tables. | [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) |
| `cdstubs` | `mbdump-cdstubs.tar.bz2` | `musicbrainz` | CDStubs. | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) |

Example: `--modules core,derived,cover-art`.

The canonical enumeration of these archives — their contents, licensing, and release cadence — lives on the [MusicBrainz Database / Download wiki page](https://wiki.musicbrainz.org/MusicBrainz_Database/Download).

## Commands

- `list-dumps` — print the dated dump directories on the mirror.
- `download` — fetch the selected archives (SHA256-verified, resumable).
- `schema create` — fetch `admin/sql/*.sql` at `--ref` and apply pre- and/or post-import DDL.
- `import` — stream TSVs from a local `--dump-dir` through `COPY FROM STDIN`.
- `run` — end-to-end: pick or resolve a dump, download, pre-DDL, import, post-DDL, `VACUUM ANALYZE`.
- `verify` — print `SCHEMA_SEQUENCE` / `REPLICATION_SEQUENCE` for each local archive.
- `clean` — remove cached downloads.

## Configuration

Precedence: CLI flags > env vars > `.env` file > defaults.

| Variable | Meaning |
|---|---|
| `MUSICBRAINZ_DATABASE_SETUP_DB_URL` | libpq connection URL |
| `MUSICBRAINZ_DATABASE_SETUP_MIRROR_URL` | Base URL of the dump mirror |
| `MUSICBRAINZ_DATABASE_SETUP_SQL_REF` | Git ref (branch/tag/SHA) for the `admin/sql/*.sql` fetch |
| `MUSICBRAINZ_DATABASE_SETUP_WORKDIR` | Local cache dir for archive downloads |
| `MUSICBRAINZ_DATABASE_SETUP_MODULES` | Default module list |

## Scope

- One-shot full imports only. Replication packets (`LATEST-replication`) are out of scope for v1.
- Fetches admin SQL from [`metabrainz/musicbrainz-server`](https://github.com/metabrainz/musicbrainz-server) on GitHub at a configurable git ref. Default is `master`; pin to a `v-NN-schema-change` tag for full reproducibility.

## Status

>  This project is under active development.

### What's already implemented

- Listing dated dumps on the MetaBrainz mirror and resolving `LATEST`.
- Interactive picker for dated dumps when `--date` / `--latest` / `--dump-dir` are all omitted.
- Resumable downloads with SHA256 verification (`.part` file renamed only after the digest matches).
- Fetching `admin/sql/*.sql` from upstream `metabrainz/musicbrainz-server` at a configurable git ref, cached on disk keyed by resolved commit SHA.
- Applying DDL files via `psql` in the canonical `admin/InitDb.pl` phase order (Extensions → Collations → Types → Tables → COPY → PrimaryKeys → Functions → Indexes → FKs → Constraints → Sequences → Views → Triggers).
- Streaming TSV archive members into `COPY FROM STDIN` via psycopg 3, with no intermediate disk extraction.
- Per-archive and per-table progress bars via `rich`.
- Idempotent reruns via `musicbrainz_database_setup.applied_phases` and `musicbrainz_database_setup.imported_archives` bookkeeping tables.
- All ten dump modules: `core`, `derived`, `editor`, `edit`, `cover-art`, `event-art`, `stats`, `documentation`, `wikidocs`, `cdstubs`.
- Pre-flights for the required contrib extensions, ICU support on the server, and `psql` on the client.

See [CHANGELOG.md](CHANGELOG.md) for the full list of implemented features, fixes, implementation plans, feature documentation and session transcripts.

### What's coming

- **`SCHEMA_SEQUENCE` cross-check** — compare the dump archive's `SCHEMA_SEQUENCE` file against the `current_schema_sequence` value in the fetched `CreateTables.sql` and fail hard on mismatch, so silently pointing the tool at an incompatible upstream `--ref` can't corrupt an import. `--allow-schema-mismatch` as an escape hatch.

## Development

For running the test suite, linting, or type-checking, install with the `dev` extra:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src tests
uv run mypy src
```

## References

This tool is built on the following primary sources:

- **MusicBrainz wiki — Database / Download** — https://wiki.musicbrainz.org/MusicBrainz_Database/Download — mirror layout, dump cadence, checksum/signature files.
- **MusicBrainz wiki — Database / Schema** — https://wiki.musicbrainz.org/MusicBrainz_Database/Schema — PG version and extension requirements.
- **MusicBrainz Entity** — https://musicbrainz.org/doc/MusicBrainz_Entity — the entity model and which entities are core vs derived.
- **MusicBrainz wiki — Development / JSON Data Dumps** — https://musicbrainz.org/doc/Development/JSON_Data_Dumps — JSON dump format (out of scope for this tool).
- **`musicbrainz-server/admin/sql/`** — https://github.com/metabrainz/musicbrainz-server/tree/master/admin/sql — the canonical DDL this tool applies (`Extensions.sql`, `CreateCollations.sql`, `CreateTypes.sql`, `CreateTables.sql`, …, `CreateTriggers.sql`).
- **`musicbrainz-server/admin/`** — https://github.com/metabrainz/musicbrainz-server/tree/master/admin — `InitDb.pl` (authoritative DDL phase order) and `MBImport.pl` (reference for the COPY loop).
- **`metabrainz/musicbrainz-docker`** — https://github.com/metabrainz/musicbrainz-docker — upstream's official Docker-compose stack. A useful reference for how upstream provisions Postgres, but not a dependency of this tool.
- **`acoustid/mbslave`** — https://github.com/acoustid/mbslave — Lukas Lalinsky's Python tool that handles both initial import and ongoing replication.
- **`acoustid/mbdata`** — https://github.com/acoustid/mbdata — SQLAlchemy models for the MusicBrainz schema. Complementary to this tool.
- **`postgres` Docker image** — https://hub.docker.com/_/postgres — the official image used in the Quick start.

## License

[MIT](LICENSE) — © 2026 Rafael Cordones.
