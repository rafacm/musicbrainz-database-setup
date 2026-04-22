# Prerequisites

Before running `musicbrainz-db-setup`, the target PostgreSQL server and the machine running the tool must satisfy the following.

## PostgreSQL server

The tool needs a PostgreSQL 16+ server with three stock extensions (`cube`, `earthdistance`, `unaccent`) and two MusicBrainz-specific C extensions (`musicbrainz_collate`, `musicbrainz_unaccent`). The repository ships a Docker image that has all of this baked in on top of `postgres:16` — that's the fastest path to a working server.

### Build the image

```bash
docker build -t musicbrainz-db-setup-pg:16 tests/docker/
```

### Start the container

```bash
docker run -d \
    --name musicbrainz-pg \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    -v musicbrainz-pg-data:/var/lib/postgresql/data \
    musicbrainz-db-setup-pg:16
```

The `postgres:16` base image's entrypoint creates a `postgres` superuser from `POSTGRES_PASSWORD` on first boot, so the container is immediately usable with `musicbrainz-db-setup`:

```bash
uv run musicbrainz-db-setup run \
    --db postgresql://postgres:postgres@localhost:5432/postgres \
    --modules core --latest
```

### Create a dedicated superuser (optional)

If you'd rather not use the default `postgres` role, create a dedicated superuser and database:

```bash
docker exec -i musicbrainz-pg psql -U postgres <<'SQL'
CREATE ROLE mb WITH LOGIN SUPERUSER PASSWORD 'mb';
CREATE DATABASE musicbrainz OWNER mb;
SQL
```

Then point the tool at the new role:

```bash
uv run musicbrainz-db-setup run \
    --db postgresql://mb:mb@localhost:5432/musicbrainz \
    --modules core --latest
```

### Pointing at a pre-existing PostgreSQL server

If you're running against an existing server rather than the image above, the host must provide:

- **PostgreSQL 16 or later** — MusicBrainz's upstream schema assumes PG 16+.
- **`postgresql-contrib`** (Debian/Ubuntu) or your distro's equivalent — supplies `cube`, `earthdistance`, and `unaccent`.
- **The MusicBrainz custom C extensions**, compiled against the server's major version. On the PG server host:

  ```bash
  sudo apt-get install postgresql-server-dev-16 build-essential
  git clone https://github.com/metabrainz/musicbrainz-server.git
  cd musicbrainz-server/postgresql-extensions
  make && sudo make install
  ```

  The tool calls `SELECT name FROM pg_available_extensions` at startup and aborts with a pointer back here if either extension is missing.

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
