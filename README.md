<p align="center">
  <img src="docs/assets/musicbrainz-database-setup.png" alt="MusicBrainz Data Dumps to PostgreSQL, in one beat" width="350" />
</p>

<p align="center">
  <strong>MusicBrainz Data Dumps to PostgreSQL, in one beat</strong>
</p>

<p align="center">
  <a href="https://github.com/rafacm/musicbrainz-database-setup/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/rafacm/musicbrainz-database-setup/actions/workflows/ci.yml/badge.svg" /></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.11 | 3.12 | 3.13" src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg" /></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green.svg" /></a>
</p>

<br/>

`musicbrainz-database-setup` is a Python CLI that sets up a full [MusicBrainz](https://musicbrainz.org/) database in a PostgreSQL instance of your choice. It downloads the official dumps from the MetaBrainz mirror, creates the [schema](https://wiki.musicbrainz.org/MusicBrainz_Database/Schema) by running the upstream `admin/sql/*.sql` [files](https://github.com/metabrainz/musicbrainz-server/tree/master/admin/sql) against your database, and loads the data straight from the archives into your database — with resumable downloads, verified integrity, and live progress for every table.

This tool brings together the steps documented across the [MusicBrainz wiki](https://wiki.musicbrainz.org/MusicBrainz_Database/Download), the `musicbrainz-server` [admin Perl scripts](https://github.com/metabrainz/musicbrainz-server/tree/master/admin), and the [`metabrainz/musicbrainz-docker`](https://github.com/metabrainz/musicbrainz-docker) stack into a single command you can point at any PostgreSQL connection.

## Requirements

- PostgreSQL **16 or later** — any official [`postgres:*` Docker image](https://hub.docker.com/_/postgres) satisfies every server-side requirement out of the box.
- A role with **`SUPERUSER`** on the target DB (the default `postgres` user works).
- **`psql`** on your `$PATH` on the machine running the tool.
- **~30 GB** of free disk for `core + derived` downloads; **~160 GB** for the live DB once indexes are built.

See [Requirements in detail](#requirements-in-detail) for the full list, including managed-PostgreSQL notes.

## Quick start

### Start a Postgres instance

Any official `postgres:*` image works. `--name` is the Docker container name (for `docker exec` / `docker stop`); the database name used by the tool is `postgres`, the default created by the image's entrypoint.

```bash
docker run -d \
  --name musicbrainz-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:17-alpine
```

### Install the CLI

```bash
uv sync
```

### Download, create the schema, import, and finalise, end-to-end

Connection string is `postgresql://<user>:<password>@<host>:<port>/<database>`.

```bash
uv run musicbrainz-database-setup run \
  --db postgresql://postgres:postgres@localhost:5432/postgres \
  --modules core \
  --latest
```

If neither `--latest` nor `--date YYYYMMDD-HHMMSS` is passed, `run` interactively prompts for a dump directory from the mirror.

### Poke around the imported data

Open a psql session against the running container and run a couple of sanity queries:

```bash
docker exec -it musicbrainz-postgres psql -U postgres -d postgres
```

```sql
-- Row counts of the top-level entities
SELECT
  (SELECT count(*) FROM musicbrainz.artist)    AS artists,
  (SELECT count(*) FROM musicbrainz.release)   AS releases,
  (SELECT count(*) FROM musicbrainz.recording) AS recordings;

-- Look up an artist by name (gid is the MusicBrainz ID / MBID)
SELECT gid, name, sort_name FROM musicbrainz.artist WHERE name = 'The Beatles';
```

For the full entity model and table-by-table reference, see the [MusicBrainz Database](https://musicbrainz.org/doc/MusicBrainz_Database) and [Database Schema](https://musicbrainz.org/doc/MusicBrainz_Database/Schema) docs.

## Modules

The MusicBrainz database is split across several `.tar.bz2` archives on the mirror — enumerated canonically, with contents, licensing, and release cadence, on the [MusicBrainz Database / Download wiki page](https://wiki.musicbrainz.org/MusicBrainz_Database/Download).

`--modules` (comma-separated) selects which to download and import; `core` is the default and the others are opt-in. Example: `--modules core,derived,cover-art`.

| Module | Target schema | Contents |
|---|---|---|
| `core` | `musicbrainz` | Core MusicBrainz database — tables for Artist, Release, Recording, etc. Most catalog use cases only need this plus `derived`. |
| `derived` | `musicbrainz` | Annotations, user ratings, user tags, and search indexes. Required for genre data (genres are stored as user tags). Annotations FK to editors, so add `editor` for standalone (non-mirror) setups. |
| `editor` | `musicbrainz` | Non-personal user data about the people who enacted the edits in the edit history. |
| `edit` | `musicbrainz` | Complete edit history for the core database — open and closed edits, edit notes, votes, and auto-editor elections. Editor identity comes from the `editor` dump. |
| `cover-art` | `cover_art_archive` | Tables linking MusicBrainz to the [Cover Art Archive](https://wiki.musicbrainz.org/Cover_Art_Archive) (metadata only — no images). |
| `event-art` | `event_art_archive` | Tables linking MusicBrainz to the [Event Art Archive](https://wiki.musicbrainz.org/Event_Art_Archive) (metadata only — no images). |
| `stats` | `statistics` | Site statistics — the data behind [musicbrainz.org/statistics](https://musicbrainz.org/statistics). |
| `documentation` | `documentation` | Tables specifying which relationships are used as examples for each relationship type, plus per-type guidelines where available. |
| `wikidocs` | `wikidocs` | The `wikidocs_index` table — which revision is transcluded for each page in the [WikiDocs](https://wiki.musicbrainz.org/WikiDocs) system. |
| `cdstubs` | `musicbrainz` | [CD Stubs](https://wiki.musicbrainz.org/CD_Stub) — anonymously submitted, treated as an untrusted source kept separate from the core database. |

## Supported commands

Run `uv run musicbrainz-database-setup --help` to see the available commands and options at any time.

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
| `MUSICBRAINZ_DATABASE_SETUP_SQL_REF` | Git ref (branch/tag/SHA) for the `admin/sql/*.sql` fetch. Default `master`; pin to a `v-NN-schema-change` tag for reproducibility. |
| `MUSICBRAINZ_DATABASE_SETUP_WORKDIR` | Local cache dir for archive downloads. Default `${XDG_CACHE_HOME:-~/.cache}/musicbrainz-database-setup/dumps`. |
| `MUSICBRAINZ_DATABASE_SETUP_SQL_CACHE_DIR` | Local cache dir for fetched `admin/sql/*.sql` files, keyed by resolved commit SHA. Default `${XDG_CACHE_HOME:-~/.cache}/musicbrainz-database-setup/sql`. |
| `MUSICBRAINZ_DATABASE_SETUP_MODULES` | Comma-separated list of modules to download and import (e.g. `core,derived,cover-art`). See [Modules](#modules). Default `core`. |

### Splitting the connection string

libpq (used by both psycopg3 and `psql`) natively honors the `PG*` environment variables — values omitted from the connection URL fall back to them. This lets you keep connection coordinates and secrets in separate places. Hard-code host/port/user/database in a committed `.env`:

```bash
MUSICBRAINZ_DATABASE_SETUP_DB_URL=postgresql://postgres@localhost:5432/postgres
```

…and supply the password at runtime from a secret manager or your shell:

```bash
PGPASSWORD="$(op read op://work/musicbrainz/password)" \
  uv run musicbrainz-database-setup run --latest
```

Any libpq [environment variable](https://www.postgresql.org/docs/current/libpq-envars.html) works the same way (`PGSSLMODE`, `PGSSLROOTCERT`, `PGCONNECT_TIMEOUT`, …).

## Status

>  This project is under active development.

### What's already implemented

- Dump discovery — mirror listing, `LATEST` resolution, and an interactive picker when `--date` / `--latest` / `--dump-dir` are omitted.
- Resumable, SHA256-verified downloads.
- Upstream admin SQL fetched at a configurable git ref and applied via `psql` in the canonical `admin/InitDb.pl` phase order.
- Streaming TSV → `COPY FROM STDIN` with per-archive and per-table progress bars, across all ten dump modules.
- Idempotent reruns; pre-flights for required extensions, ICU support, and `psql` on the client.

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

## Requirements in detail

PostgreSQL **16 or later** with:

- The **`cube`**, **`earthdistance`**, and **`unaccent`** extensions — declared in upstream [`admin/sql/Extensions.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/Extensions.sql). They ship with the `postgresql-contrib` package, which is bundled in every official [`postgres:*` Docker image](https://hub.docker.com/_/postgres).
- **ICU support** (server built with `--with-icu`). The MusicBrainz collation in [`admin/sql/CreateCollations.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/CreateCollations.sql) uses `provider = icu`. Every official `postgres:*` image since PG 16 qualifies.
- A role with **`SUPERUSER`** privileges so the tool can `CREATE EXTENSION`. The default `postgres` user created by the official image works.

The tool pre-flights `pg_available_extensions` and `pg_collation` at startup and aborts with an actionable message if anything is missing.

The **`psql` client** must be available on `$PATH` on the machine running the tool. The upstream `admin/sql/*.sql` files use psql meta-commands (`\set ON_ERROR_STOP 1`, etc.) and manage their own `BEGIN;/COMMIT;` — we shell out to `psql` for each file, mirroring `admin/InitDb.pl`'s own approach, rather than reimplementing that parsing in Python. Install it with `brew install libpq` (macOS), `apt install postgresql-client` (Debian/Ubuntu), `apk add postgresql-client` (Alpine), or the equivalent on your distro.

**Disk:** expect ~10–15 GB of downloads for `core`, ~30 GB for `core + derived`, and the live database grows to roughly 100–160 GB once indexes are built. More if `cover-art` or `event-art` are selected.

The tool also works against managed PostgreSQL (RDS, Cloud SQL, etc.) as long as the role you connect as can `CREATE EXTENSION` (on RDS that's `rds_superuser`; on Cloud SQL, `postgres`).

## References

This tool is built on the following primary sources.

### MusicBrainz documentation

- [**Database / Download**](https://wiki.musicbrainz.org/MusicBrainz_Database/Download): mirror layout, dump cadence, checksum/signature files.
- [**Database / Schema**](https://wiki.musicbrainz.org/MusicBrainz_Database/Schema): PG version and extension requirements.
- [**MusicBrainz Entity**](https://musicbrainz.org/doc/MusicBrainz_Entity): the entity model and which entities are core vs derived.
- [**Development / JSON Data Dumps**](https://musicbrainz.org/doc/Development/JSON_Data_Dumps): JSON dump format (out of scope for this tool).

### Upstream code

- [**`metabrainz/musicbrainz-server/admin/sql/`**](https://github.com/metabrainz/musicbrainz-server/tree/master/admin/sql): the canonical DDL this tool applies (`Extensions.sql`, `CreateCollations.sql`, `CreateTypes.sql`, `CreateTables.sql`, …, `CreateTriggers.sql`).
- [**`metabrainz/musicbrainz-server/admin/`**](https://github.com/metabrainz/musicbrainz-server/tree/master/admin): `InitDb.pl` (authoritative DDL phase order) and `MBImport.pl` (reference for the COPY loop).
- [**`metabrainz/musicbrainz-docker`**](https://github.com/metabrainz/musicbrainz-docker): upstream's official Docker-compose stack. A useful reference for how upstream provisions Postgres, but not a dependency of this tool.

### Related Python tools

- [**`acoustid/mbslave`**](https://github.com/acoustid/mbslave): Lukas Lalinsky's Python tool that handles both initial import and ongoing replication.
- [**`acoustid/mbdata`**](https://github.com/acoustid/mbdata): SQLAlchemy models for the MusicBrainz schema. Complementary to this tool.

### PostgreSQL

- [**`postgres` Docker image**](https://hub.docker.com/_/postgres): the official image used in the Quick start.

## License

[MIT](LICENSE) — © 2026 Rafael Cordones.
