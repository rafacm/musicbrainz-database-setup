# Prerequisites

Before running `musicbrainz-db-setup`, the target PostgreSQL server and the machine running the tool must satisfy the following.

## PostgreSQL server

- **PostgreSQL 16 or later.** MusicBrainz's upstream schema assumes PG 16+.
- **`postgresql-contrib`** (Debian/Ubuntu) or your distro's equivalent, which provides the `cube`, `earthdistance`, and `unaccent` extensions.
- **MusicBrainz custom C extensions**, built against your server's major version:
  - `musicbrainz_collate` — provides the `musicbrainz` collation used across text columns.
  - `musicbrainz_unaccent` — provides the immutable unaccent function used in indexes.

  Historically these ship inside the `musicbrainz-server` repository under `postgresql-extensions/` (and/or the `musicbrainz-docker` images). To build them manually:

  ```bash
  # on the PG server host
  sudo apt-get install postgresql-server-dev-16 build-essential
  git clone https://github.com/metabrainz/musicbrainz-server.git
  cd musicbrainz-server/postgresql-extensions
  make && sudo make install
  ```

  The tool calls `SELECT name FROM pg_available_extensions` at startup; if either is missing it aborts with an explicit pointer back here.

- **A role with `SUPERUSER`** (or at minimum: `CREATEDB`, `CREATEROLE`, membership in `pg_read_server_files`, plus the right to `CREATE EXTENSION`). The simplest path is the default `postgres` superuser.

## Disk and network

- ~30 GB network transfer for `core + derived`.
- ~120 GB disk for the downloaded archives.
- ~160 GB disk for the live database once indexes are built.
- These figures grow significantly if `cover-art` or `event-art` are selected.

## Client machine

- **Python 3.11+** (the CLI auto-resolves via `uv`).
- **`uv`** for running the tool as a dev-mode install (`uv sync && uv run musicbrainz-db-setup ...`).
- **`gpg`** on `$PATH` *only if* you pass `--verify-gpg`. Otherwise SHA256 checksums are used.

## Network access

- `https://data.metabrainz.org` for the dump mirror.
- `https://raw.githubusercontent.com` and `https://api.github.com` for the upstream `admin/sql/*.sql` files.
