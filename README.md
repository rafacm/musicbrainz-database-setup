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

`musicbrainz-database-setup` is a Python CLI that sets up a full [MusicBrainz](https://musicbrainz.org/) database in PostgreSQL. Point it at a connection string and a dump, and it handles the rest: resumable, SHA256-verified downloads from the [MetaBrainz mirror](https://wiki.musicbrainz.org/MusicBrainz_Database/Download), schema creation via the upstream [`admin/sql/*.sql`](https://github.com/metabrainz/musicbrainz-server/tree/master/admin/sql) files, and streaming `COPY` of every table with live progress.

This project originated from [RAGtime](https://github.com/rafacm/ragtime), where it powers the [entity-resolution step](https://github.com/rafacm/ragtime/tree/main/doc#8--resolve-entities-status-resolving) that maps extracted mentions to canonical MusicBrainz entities.

## Requirements

- PostgreSQL **16 or later** — any official [`postgres:*` Docker image](https://hub.docker.com/_/postgres) satisfies every server-side requirement out of the box.
- A role with **`SUPERUSER`** on the target DB (the default `postgres` user works).
- **`psql`** on your `$PATH` on the machine running the tool.
- **`pbzip2`** (or **`lbzip2`**) on `$PATH` *(optional, recommended)* — parallelises bz2 decompression during COPY, the single biggest phase of a fresh import. Without it the tool falls back to CPython's single-threaded stdlib `bz2`.

See [docs/README.md](docs/README.md) for the full setup guide — extensions, ICU, server-side tuning, disk/memory, and managed-PostgreSQL notes.

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

> 💡 **Want a faster import?** Add server-start tuning flags (`shared_buffers`, `max_wal_size`, `checkpoint_timeout`, …) to roughly halve post-import DDL time. See [Server-side tuning](docs/README.md#server-side-tuning-optional) in the reference guide for the tuned `docker run` and per-flag rationale.

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

Open a psql session against the database and run a couple of sanity queries:

```bash
psql postgresql://postgres:postgres@localhost:5432/postgres
```

```sql
-- Row counts of the top-level entities
SELECT
  (SELECT count(*) FROM musicbrainz.artist)    AS artists,
  (SELECT count(*) FROM musicbrainz.release)   AS releases,
  (SELECT count(*) FROM musicbrainz.recording) AS recordings;
```

Look up [Django Reinhardt](https://musicbrainz.org/artist/650bf385-6f6d-4992-a3b9-779d144920a4) by his MBID (his Wikidata ID is [Q44122](https://www.wikidata.org/wiki/Q44122)) — joining `artist` to `gender`, `artist_type`, and `area` for the human-readable details:

```sql
SELECT
  a.gid,
  a.name,
  a.sort_name,
  g.name           AS gender,
  at.name          AS type,
  a.begin_date_year,
  a.end_date_year,
  birth_area.name  AS birth_area,
  a.comment
FROM musicbrainz.artist a
LEFT JOIN musicbrainz.gender      g          ON a.gender = g.id
LEFT JOIN musicbrainz.artist_type at         ON a.type   = at.id
LEFT JOIN musicbrainz.area        birth_area ON a.area   = birth_area.id
WHERE a.gid = '650bf385-6f6d-4992-a3b9-779d144920a4';
```

…and his external links via the URL relationship system (`l_artist_url` → `link` → `link_type` → `url`) — Wikidata, Discogs, allmusic, last.fm, IMDb, and many more:

```sql
SELECT lt.name AS link_type, u.url
FROM musicbrainz.l_artist_url lau
JOIN musicbrainz.artist    a  ON lau.entity0 = a.id
JOIN musicbrainz.link      l  ON lau.link    = l.id
JOIN musicbrainz.link_type lt ON l.link_type = lt.id
JOIN musicbrainz.url       u  ON lau.entity1 = u.id
WHERE a.gid = '650bf385-6f6d-4992-a3b9-779d144920a4'
ORDER BY lt.name;
```

For the full entity model and table-by-table reference, see the [MusicBrainz Database](https://musicbrainz.org/doc/MusicBrainz_Database) and [Database Schema](https://musicbrainz.org/doc/MusicBrainz_Database/Schema) docs.

## Modules

Pass `--modules core,derived,…` (comma-separated) to select which `.tar.bz2` archives to download and import. Default is `core`; the others are opt-in. See [available modules](docs/README.md#modules) for the full list and what each contains.

## Supported commands

Run `uv run musicbrainz-database-setup --help` to see the available commands and options at any time.

- `list-dumps`: print the dated dump directories on the mirror.
- `download`: fetch the selected archives (SHA256-verified, resumable).
- `schema create`: fetch `admin/sql/*.sql` at `--ref` and apply pre- and/or post-import DDL.
- `import`: stream TSVs from a local `--dump-dir` through `COPY FROM STDIN`.
- `run`: end-to-end — pick or resolve a dump, download, pre-DDL, import, post-DDL, `VACUUM ANALYZE`.
- `verify`: print `SCHEMA_SEQUENCE` / `REPLICATION_SEQUENCE` for each local archive.
- `clean`: remove cached downloads.

Pass `-v` / `--verbose` on any of these commands to surface the underlying DEBUG-level output (`httpx` HTTP requests and the rest of the chatter); the default transcript stays focused on high-level phase progress.

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

## Credits

This tool stands on the work of the [MusicBrainz](https://musicbrainz.org/), [MetaBrainz](https://metabrainz.org/), and [acoustid](https://acoustid.org/) communities. It automates the steps documented across the MusicBrainz wiki and the upstream [`musicbrainz-server/admin`](https://github.com/metabrainz/musicbrainz-server/tree/master/admin) Perl scripts into a single command you can point at any PostgreSQL connection — local Docker, managed (RDS, Cloud SQL), or anything else that speaks libpq. 

See [docs/README.md → References](docs/README.md#references) for the full list of upstream sources.

## License

[MIT](LICENSE) — © 2026 Rafael Cordones.
