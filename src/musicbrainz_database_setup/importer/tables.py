"""Resolves a dump's TSV filename to its target ``schema.table`` in Postgres.

For v1 we route by module:
  - archive = mbdump.tar.bz2 / derived / editor / edit / cdstubs → ``musicbrainz``
  - archive = mbdump-cover-art-archive.tar.bz2 → ``cover_art_archive``
  - archive = mbdump-event-art-archive.tar.bz2 → ``event_art_archive``
  - archive = mbdump-stats.tar.bz2 → ``statistics``
  - archive = mbdump-documentation.tar.bz2 → ``documentation``
  - archive = mbdump-wikidocs.tar.bz2 → ``wikidocs``

The COPY statement uses ``COPY <schema>.<table> FROM STDIN`` with no explicit
column list — the TSV columns match the table definition 1:1 because
``CreateTables.sql`` runs first. This matches how MBImport.pl does it.
"""

from __future__ import annotations

from musicbrainz_database_setup.sql.manifest import MODULE_ARCHIVE, MODULE_SCHEMA


def module_for_archive(archive_name: str) -> str | None:
    for module, name in MODULE_ARCHIVE.items():
        if name == archive_name:
            return module
    return None


def schema_for_archive(archive_name: str) -> str:
    module = module_for_archive(archive_name)
    if module is None:
        raise ValueError(f"Unknown archive: {archive_name}")
    return MODULE_SCHEMA[module]
