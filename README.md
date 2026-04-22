# musicbrainz-db-setup

Python CLI that downloads MusicBrainz database dumps and imports them into a PostgreSQL instance.

## Quick start

```bash
uv sync
uv run musicbrainz-db-setup --help
uv run musicbrainz-db-setup list-dumps
uv run musicbrainz-db-setup run \
    --db postgresql://postgres:postgres@localhost:5432/musicbrainz \
    --modules core \
    --latest
```

See [docs/PREREQUISITES.md](docs/PREREQUISITES.md) for the PostgreSQL server prerequisites — specifically the custom `musicbrainz_collate` / `musicbrainz_unaccent` extensions which must be compiled and installed on the server host before the tool can create collations.

## Commands

- `list-dumps` — list the dated dump directories on the mirror.
- `download` — download the selected archives (with SHA256 verify and resume).
- `schema create` — fetch `admin/sql/*.sql` from `metabrainz/musicbrainz-server` at a configurable git ref and apply them.
- `import` — stream TSVs from local archives directly into `COPY FROM STDIN`.
- `run` — end-to-end: pick/resolve a dump, download, pre-DDL, import, post-DDL.
- `verify` — print `SCHEMA_SEQUENCE`/`REPLICATION_SEQUENCE` for each local archive.
- `clean` — remove cached downloads.

Pass `--modules core,derived,cover-art` to pick modules. Valid values: `core` (default), `derived`, `editor`, `edit`, `cover-art`, `event-art`, `stats`, `documentation`, `wikidocs`, `cdstubs`.

## Configuration

Precedence: CLI flags > env vars > `.env` file > defaults. Env vars:

| Variable | Meaning |
|---|---|
| `MUSICBRAINZ_DB_SETUP_DB_URL` | libpq connection URL |
| `MUSICBRAINZ_DB_SETUP_MIRROR_URL` | Base URL of the dump mirror |
| `MUSICBRAINZ_DB_SETUP_SQL_REF` | Git ref (branch/tag/SHA) for admin/sql fetch |
| `MUSICBRAINZ_DB_SETUP_WORKDIR` | Local cache dir for archives |
| `MUSICBRAINZ_DB_SETUP_MODULES` | Default modules |

## Scope

- Default: downloads `mbdump.tar.bz2` (core catalog) and imports it.
- Opt-in via `--modules`: `derived`, `editor`, `edit`, `cover-art`, `event-art`, `stats`, `documentation`, `wikidocs`, `cdstubs`.
- One-shot full imports only. Replication packets (`LATEST-replication`) are out of scope for v1.
- Fetches admin SQL from `metabrainz/musicbrainz-server` on GitHub at a configurable git ref.

## License

MIT.
