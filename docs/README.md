# Prerequisites

Before running `musicbrainz-database-setup`, the target PostgreSQL server and the machine running the tool must satisfy the following.

## PostgreSQL server

Any official `postgres:*` image from Docker Hub works — including `postgres:17-alpine`, `postgres:17`, `postgres:16-alpine`, `postgres:16`. The tool doesn't need a custom image or any extension-build step:

- `cube`, `earthdistance`, and `unaccent` ship in `postgresql-contrib`, which is bundled with every official image. The tool runs `CREATE EXTENSION IF NOT EXISTS` itself.
- The `musicbrainz` collation used by the upstream schema is now a plain ICU collation (`CREATE COLLATION ... provider = icu`). Every official `postgres:*` image since PG 16 is built with `--with-icu`.
- `musicbrainz_unaccent` is a SQL function defined inline by `Extensions.sql`, not an extension.

### Starting a standalone container

```bash
docker run -d \
    --name musicbrainz-pg \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    -v musicbrainz-pg-data:/var/lib/postgresql/data \
    postgres:17-alpine
```

The entrypoint creates a `postgres` superuser from `POSTGRES_PASSWORD` on first boot, which is immediately usable:

```bash
uv run musicbrainz-database-setup run \
    --db postgresql://postgres:postgres@localhost:5432/postgres \
    --modules core --latest
```

### Using an existing docker-compose.yml

If your project already declares a Postgres service, no changes are required. Point `--db` at it and go:

```yaml
# your docker-compose.yml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
```

```bash
uv run musicbrainz-database-setup run --db "$DB_URL" --modules core --latest
```

### Creating a dedicated superuser (optional)

If you'd rather not use the default `postgres` role:

```bash
docker exec -i musicbrainz-pg psql -U postgres <<'SQL'
CREATE ROLE mb WITH LOGIN SUPERUSER PASSWORD 'mb';
CREATE DATABASE musicbrainz OWNER mb;
SQL
```

```bash
uv run musicbrainz-database-setup run \
    --db postgresql://mb:mb@localhost:5432/musicbrainz \
    --modules core --latest
```

### Pointing at a pre-existing bare-metal PostgreSQL server

The host PG install must provide:

- **PostgreSQL 16 or later**, built with `--with-icu` (default on every mainstream distro package).
- **`postgresql-contrib`** (Debian/Ubuntu) or your distro's equivalent — supplies `cube`, `earthdistance`, and `unaccent`.
- **A role with `SUPERUSER`** (or at minimum: `CREATEDB`, `CREATEROLE`, `pg_read_server_files` membership, plus the right to `CREATE EXTENSION`).

The tool pre-flights `pg_available_extensions` at startup and aborts with a clear pointer back here if anything is missing.

### What about managed Postgres (RDS, Cloud SQL)?

RDS, Cloud SQL, and other managed providers typically include `cube`, `earthdistance`, and `unaccent` and are built with ICU, so the pre-flight should pass. Caveats:

- The role you connect as must be allowed to `CREATE EXTENSION` — on RDS the `rds_superuser` role qualifies; on Cloud SQL the `postgres` role does.
- `COPY FROM STDIN` is supported on every managed PG. No change needed.

## Disk and network

- ~30 GB network transfer for `core + derived`.
- ~120 GB disk for the downloaded archives.
- ~160 GB disk for the live database once indexes are built.
- These figures grow significantly if `cover-art` or `event-art` are selected.

## Client machine

- **Python 3.11+** (the CLI auto-resolves via `uv`).
- **`uv`** for running the tool as a dev-mode install (`uv sync && uv run musicbrainz-database-setup ...`).
- **`gpg`** on `$PATH` *only if* you pass `--verify-gpg`. Otherwise SHA256 checksums are used.

## Network access

- `https://data.metabrainz.org` for the dump mirror.
- `https://raw.githubusercontent.com` and `https://api.github.com` for the upstream `admin/sql/*.sql` files.
