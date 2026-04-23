"""Per-module lists of SQL files to fetch and the order to execute them.

Mirrors the phases of ``admin/InitDb.pl`` in the upstream
``metabrainz/musicbrainz-server`` repo. Paths are repo-relative
(``admin/sql/...``) and resolved against the configured git ref.
"""

from __future__ import annotations

from dataclasses import dataclass

# Module identifiers used on the CLI (hyphenated) and the corresponding
# admin/sql/ subdirectory in the upstream repo.
MODULE_SUBDIR = {
    "core": "",
    "derived": "",  # derived data lives in core tables, no extra DDL
    "editor": "",
    "edit": "",
    "cover-art": "caa",
    "event-art": "eaa",
    "stats": "statistics",
    "documentation": "documentation",
    "wikidocs": "wikidocs",
    "cdstubs": "",
}

# Target Postgres schemas. Created before DDL runs.
MODULE_SCHEMA = {
    "core": "musicbrainz",
    "derived": "musicbrainz",
    "editor": "musicbrainz",
    "edit": "musicbrainz",
    "cover-art": "cover_art_archive",
    "event-art": "event_art_archive",
    "stats": "statistics",
    "documentation": "documentation",
    "wikidocs": "wikidocs",
    "cdstubs": "musicbrainz",
}

# Bz2 archive filenames on the mirror.
MODULE_ARCHIVE = {
    "core": "mbdump.tar.bz2",
    "derived": "mbdump-derived.tar.bz2",
    "editor": "mbdump-editor.tar.bz2",
    "edit": "mbdump-edit.tar.bz2",
    "cover-art": "mbdump-cover-art-archive.tar.bz2",
    "event-art": "mbdump-event-art-archive.tar.bz2",
    "stats": "mbdump-stats.tar.bz2",
    "documentation": "mbdump-documentation.tar.bz2",
    "wikidocs": "mbdump-wikidocs.tar.bz2",
    "cdstubs": "mbdump-cdstubs.tar.bz2",
}


@dataclass(frozen=True, slots=True)
class SqlFile:
    module: str  # "core", "cover-art", ...
    repo_path: str  # e.g. "admin/sql/CreateTables.sql"


# Core files in InitDb.pl order, split into pre-import (run before COPY) and
# post-import (run after COPY).

_CORE_PRE = [
    "admin/sql/Extensions.sql",
    "admin/sql/CreateCollations.sql",
    "admin/sql/CreateSearchConfiguration.sql",
    "admin/sql/CreateTypes.sql",
    "admin/sql/CreateTables.sql",
]

_CORE_POST = [
    "admin/sql/CreatePrimaryKeys.sql",
    "admin/sql/CreateFunctions.sql",
    "admin/sql/CreateIndexes.sql",
    "admin/sql/CreateFKConstraints.sql",
    "admin/sql/CreateConstraints.sql",
    "admin/sql/SetSequences.sql",
    "admin/sql/CreateViews.sql",
    "admin/sql/CreateTriggers.sql",
]


def _module_pre(module: str) -> list[str]:
    sub = MODULE_SUBDIR[module]
    if not sub:
        return []
    return [f"admin/sql/{sub}/CreateTables.sql"]


def _module_post(module: str) -> list[str]:
    sub = MODULE_SUBDIR[module]
    if not sub:
        return []
    return [
        f"admin/sql/{sub}/CreatePrimaryKeys.sql",
        f"admin/sql/{sub}/CreateIndexes.sql",
        f"admin/sql/{sub}/CreateFKConstraints.sql",
    ]


def pre_import_files(modules: tuple[str, ...]) -> list[SqlFile]:
    files = [SqlFile("core", p) for p in _CORE_PRE]
    for mod in modules:
        if mod == "core":
            continue
        files.extend(SqlFile(mod, p) for p in _module_pre(mod))
    return files


def post_import_files(modules: tuple[str, ...]) -> list[SqlFile]:
    files = [SqlFile("core", p) for p in _CORE_POST]
    for mod in modules:
        if mod == "core":
            continue
        files.extend(SqlFile(mod, p) for p in _module_post(mod))
    return files


def required_schemas(modules: tuple[str, ...]) -> list[str]:
    seen: dict[str, None] = {}
    for m in modules:
        seen[MODULE_SCHEMA[m]] = None
    return list(seen)


def archives_for(modules: tuple[str, ...]) -> list[str]:
    return [MODULE_ARCHIVE[m] for m in modules]
