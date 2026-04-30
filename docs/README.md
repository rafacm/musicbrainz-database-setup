# Reference guide

Long-form companion to the [project README](../README.md). Everything here is reference material — the README covers the quick-start path; this file covers what you need once you outgrow it.

## Contents

- [PostgreSQL](#postgresql)
  - [Server](#server)
  - [Server-side tuning (optional)](#server-side-tuning-optional)
  - [Client (`psql`)](#client-psql)
- [Parallel bz2 decompression (`pbzip2` / `lbzip2`, optional)](#parallel-bz2-decompression-pbzip2--lbzip2-optional)
- [Disk and memory](#disk-and-memory)
- [Modules](#modules)
- [Configuration](#configuration)
  - [Splitting the connection string](#splitting-the-connection-string)
- [References](#references)
  - [MusicBrainz documentation](#musicbrainz-documentation)
  - [Upstream code](#upstream-code)
  - [Related projects](#related-projects)
- [Regenerating the README demo GIF](#regenerating-the-readme-demo-gif)

## PostgreSQL

### Server

PostgreSQL **16 or later** with:

- The **`cube`**, **`earthdistance`**, and **`unaccent`** extensions — declared in upstream [`admin/sql/Extensions.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/Extensions.sql). They ship with the `postgresql-contrib` package, which is bundled in every official [`postgres:*` Docker image](https://hub.docker.com/_/postgres).
- **ICU support** (server built with `--with-icu`). The MusicBrainz collation in [`admin/sql/CreateCollations.sql`](https://github.com/metabrainz/musicbrainz-server/blob/master/admin/sql/CreateCollations.sql) uses `provider = icu`. Every official `postgres:*` image since PG 16 qualifies.
- A role with **`SUPERUSER`** privileges so the tool can `CREATE EXTENSION`. The default `postgres` user created by the official image works.

The tool pre-flights `pg_available_extensions` and `pg_collation` at startup and aborts with an actionable message if anything is missing.

The tool also works against managed PostgreSQL (RDS, Cloud SQL, etc.) as long as the role you connect as can `CREATE EXTENSION` (on RDS that's `rds_superuser`; on Cloud SQL, `postgres`).

### Server-side tuning (optional)

Stock Postgres defaults (`shared_buffers=128 MB`, `maintenance_work_mem=64 MB`, `synchronous_commit=on`, `max_wal_size=1 GB`) leave significant performance on the table during index builds and constraint validation. The tool sets per-session tuning via `PGOPTIONS` for every `admin/sql/*.sql` invocation, but a handful of server-side knobs can only be set on the running instance. Four of them are SIGHUP-reloadable (`pg_reload_conf()` is enough — no Postgres restart required) and roughly halve post-import DDL time. Apply them before the import and revert after:

```bash
# Before — apply tuning
psql "$DB_URL" <<'SQL'
ALTER SYSTEM SET max_wal_size = '8GB';
ALTER SYSTEM SET checkpoint_timeout = '30min';
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET random_page_cost = 1.1;
SELECT pg_reload_conf();
SQL

# Run the import
uvx --from git+https://github.com/rafacm/musicbrainz-database-setup \
  musicbrainz-database-setup run --db "$DB_URL" --modules core --latest

# After — revert tuning
psql "$DB_URL" <<'SQL'
ALTER SYSTEM RESET max_wal_size;
ALTER SYSTEM RESET checkpoint_timeout;
ALTER SYSTEM RESET effective_io_concurrency;
ALTER SYSTEM RESET random_page_cost;
SELECT pg_reload_conf();
SQL
```

- `max_wal_size=8GB` + `checkpoint_timeout=30min` — default 1 GB / 5 min triggers checkpoints every couple of minutes during COPY.
- `effective_io_concurrency=200` + `random_page_cost=1.1` — signal to the planner that the underlying storage (Docker named volume on SSD) isn't a spinning disk.

`ALTER SYSTEM` requires a role with **`SUPERUSER`** privileges (or `pg_alter_system` membership on PG 16+). The default `postgres` user from the official Docker image qualifies. Settings are server-wide — they affect every database on the instance for as long as they're applied — so `pg_reload_conf()` after the RESET block returns the instance to its prior config without leaving anything behind.

> 💡 **Power users with control over Postgres startup.** A fifth knob — `shared_buffers=2GB` — gives a further win during CHECK/FK full-table scans, but it's `postmaster`-only: it can't be reloaded; the server has to be restarted. If you spin up Postgres yourself (e.g. `docker run … postgres:17-alpine -c shared_buffers=2GB`) you can pin it at startup. We don't include it in the `psql` blocks above because the tool's audience usually has a Postgres they don't want to restart.

> ⚠️ **Memory sizing.** The tool applies `maintenance_work_mem=1GB` per psql session during DDL, and CREATE INDEX can fan out to `1 + max_parallel_maintenance_workers` workers each using that budget — up to **5 GB peak** on a single statement. On an 8 GB Docker Desktop VM that leaves comfortable headroom for the OS and page cache. If you've also pinned `shared_buffers=2GB` at server start, budget ~7 GB of Postgres memory total; pushing `shared_buffers` higher on an 8 GB VM risks OOM kills during `CreateFKConstraints.sql` / `CreateConstraints.sql` — we hit this on 2026-04-24 with `shared_buffers=4GB`.

### Client (`psql`)

The **`psql` client** must be available on `$PATH` on the machine running the tool. The upstream `admin/sql/*.sql` files use psql meta-commands (`\set ON_ERROR_STOP 1`, etc.) and manage their own `BEGIN;/COMMIT;` — we shell out to `psql` for each file, mirroring `admin/InitDb.pl`'s own approach, rather than reimplementing that parsing in Python. Install it with `brew install libpq` (macOS), `apt install postgresql-client` (Debian/Ubuntu), `apk add postgresql-client` (Alpine), or the equivalent on your distro.

## Parallel bz2 decompression (`pbzip2` / `lbzip2`, optional)

MusicBrainz dumps ship as `.tar.bz2`, and CPython's stdlib `bz2` module is single-threaded — the decompressor tops out around 35 MB/s of compressed input on a modern laptop, which pins one Python core at 100% and leaves the Postgres backend waiting on `Client/ClientRead` for most of the COPY phase. On a 14-core machine this made COPY the dominant cost of a fresh core-module import (14 m of 27 m total). If **`pbzip2`** or **`lbzip2`** is on `$PATH`, `open_archive()` pipes the archive through it instead, so decompression runs across multiple cores and the bottleneck shifts to Postgres (where it belongs). Install with `brew install pbzip2` (macOS), `apt install pbzip2` (Debian/Ubuntu), or `apk add pbzip2` (Alpine). If neither is present the tool falls back to the stdlib decompressor transparently — nothing fails, just slower.

## Disk and memory

Expect **~10–15 GB** of downloads for `core`, **~30 GB** for `core + derived`, and the live database grows to roughly **100–160 GB** once indexes are built. More if `cover-art` or `event-art` are selected.

Memory is comfortable at **8 GB** for the Postgres container with the tuning above (`shared_buffers=2GB` + the per-session `maintenance_work_mem=1GB` applied during DDL); **16 GB** if you're running the client and the database on the same machine. CPython's stdlib `bz2` fallback adds no client-side memory pressure; `pbzip2` uses a small fixed buffer per thread.

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
  uvx --from git+https://github.com/rafacm/musicbrainz-database-setup \
    musicbrainz-database-setup run --latest

# or, from a checkout:
PGPASSWORD="$(op read op://work/musicbrainz/password)" \
  uv run musicbrainz-database-setup run --latest
```

Any libpq [environment variable](https://www.postgresql.org/docs/current/libpq-envars.html) works the same way (`PGSSLMODE`, `PGSSLROOTCERT`, `PGCONNECT_TIMEOUT`, …).

## References

### MusicBrainz documentation

- [Database / Download](https://wiki.musicbrainz.org/MusicBrainz_Database/Download): mirror layout, dump cadence, checksum/signature files.
- [Database / Schema](https://wiki.musicbrainz.org/MusicBrainz_Database/Schema): PG version and extension requirements.
- [MusicBrainz Entity](https://musicbrainz.org/doc/MusicBrainz_Entity): the entity model and which entities are core vs derived.

### Upstream code

- [`metabrainz/musicbrainz-server/admin/`](https://github.com/metabrainz/musicbrainz-server/tree/master/admin): the upstream admin tree. Its [`sql/*.sql`](https://github.com/metabrainz/musicbrainz-server/tree/master/admin/sql) files are the canonical DDL we apply (`Extensions.sql`, `CreateCollations.sql`, `CreateTypes.sql`, `CreateTables.sql`, …, `CreateTriggers.sql`); `InitDb.pl` is the authoritative phase order; `MBImport.pl` is the reference for our COPY loop.

### Related projects

- [`acoustid/mbslave`](https://github.com/acoustid/mbslave): Lukas Lalinsky's Python tool that handles both initial import and ongoing replication.
- [`acoustid/mbdata`](https://github.com/acoustid/mbdata): SQLAlchemy models for the MusicBrainz schema. Complementary to this tool.
- [`metabrainz/musicbrainz-docker`](https://github.com/metabrainz/musicbrainz-docker): upstream's official Docker-compose stack — useful reference for how upstream provisions Postgres.

## Regenerating the README demo GIF

The animated terminal demo at the top of the [project README](../README.md) is generated from an [asciinema](https://asciinema.org/) recording rendered to GIF with [agg](https://github.com/asciinema/agg). Both, plus the rendering font, are available via Homebrew:

```bash
brew install asciinema agg
brew install --cask font-cascadia-mono
```

1. **Record** — spins up an [import-tuned](#server-side-tuning-optional) Postgres on `localhost:5432` and launches `asciinema` with a stripped prompt so the GIF stays clean. Run your demo commands against the printed connection string, then press `Ctrl-D` to stop. Both the port and the container name are optional positional args:

   ```bash
   mise run docs:demo-record
   # or, if 5432 is taken:
   mise run docs:demo-record 5433
   # full form:
   mise run docs:demo-record 5433 my-demo-container
   ```

2. **Render** — converts the `.cast` into `docs/assets/musicbrainz-database-setup.gif`. Playback speed, FPS cap, and `agg` theme are optional positional args (defaults: `10`, `60`, `monokai`):

   ```bash
   mise run docs:demo-render
   # tweak any/all:
   mise run docs:demo-render 8 30 dracula
   ```

3. **Cleanup** — removes the demo Postgres container (and its anonymous volume):

   ```bash
   mise run docs:postgres-stop musicbrainz-database-setup-demo
   ```

Both the `.cast` and the `.gif` are committed; the `.cast` is the source of truth, and re-rendering only requires step 2.

The record task builds on three reusable container helpers, available directly if you want a Postgres for ad-hoc demoing or local imports:

- `mise run docs:postgres-start <port> <container>` — start a stock `postgres:17-alpine` container, with an `lsof` port preflight that fails fast on collision.
- `mise run docs:postgres-start-optimized <port> <container>` — same, plus the import-tuned flags from [Server-side tuning](#server-side-tuning-optional).
- `mise run docs:postgres-stop <container>` — stop and remove a container (anonymous volume included).

> 💡 We need  `Cascadia Mono` because it's the only common monospace font that ships the Braille block (U+2800–U+28FF) used by `rich`'s default spinner. The popular programming-font families on macOS — FiraCode, Meslo, Hack, JetBrains Mono, even DejaVu Sans Mono — all strip Braille from their monospace variants. agg/usvg's font fallback only resolves missing family names, not missing glyph coverage, so the primary font has to cover everything. If you swap fonts, verify the spinner renders — a missing Braille glyph displays as `?`.
[`mise`](https://mise.jdx.dev/) tasks wrap the workflow:
