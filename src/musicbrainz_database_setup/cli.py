"""Typer CLI for musicbrainz-database-setup."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer

from musicbrainz_database_setup import __version__, config, verify
from musicbrainz_database_setup.db import connect
from musicbrainz_database_setup.errors import MBSetupError, UserError
from musicbrainz_database_setup.importer.copy import import_archive
from musicbrainz_database_setup.logging import configure, get_console
from musicbrainz_database_setup.mirror import download as dl
from musicbrainz_database_setup.mirror.index import (
    DumpDirectory,
    build_dated_dir,
    list_dated_dirs,
    resolve_latest,
)
from musicbrainz_database_setup.progress import progress_session
from musicbrainz_database_setup.schema.orchestrator import Orchestrator
from musicbrainz_database_setup.schema.phases import Phase
from musicbrainz_database_setup.sql import github, manifest

app = typer.Typer(
    name="musicbrainz-database-setup",
    no_args_is_help=True,
    add_completion=False,
    help="Download MusicBrainz database dumps and import them into PostgreSQL.",
)
schema_app = typer.Typer(help="Schema DDL management.", no_args_is_help=True)
app.add_typer(schema_app, name="schema")

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- common

DbOption = Annotated[
    str | None,
    typer.Option(
        "--db",
        envvar="MUSICBRAINZ_DATABASE_SETUP_DB_URL",
        help="PostgreSQL connection URL.",
    ),
]
ModulesOption = Annotated[
    str,
    typer.Option(
        "--modules",
        envvar="MUSICBRAINZ_DATABASE_SETUP_MODULES",
        help=(
            "Comma-separated modules: core,derived,editor,edit,cover-art,"
            "event-art,stats,documentation,wikidocs,cdstubs."
        ),
    ),
]
MirrorOption = Annotated[
    str,
    typer.Option(
        "--mirror",
        envvar="MUSICBRAINZ_DATABASE_SETUP_MIRROR_URL",
        help="Base URL of the MusicBrainz dump mirror.",
    ),
]
RefOption = Annotated[
    str,
    typer.Option(
        "--ref",
        envvar="MUSICBRAINZ_DATABASE_SETUP_SQL_REF",
        help="Git ref (branch/tag/SHA) for admin/sql/*.sql.",
    ),
]
WorkdirOption = Annotated[
    Path | None,
    typer.Option(
        "--workdir",
        envvar="MUSICBRAINZ_DATABASE_SETUP_WORKDIR",
        help="Where to store downloaded archives.",
    ),
]


@app.callback()
def _global(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False,
    quiet: Annotated[bool, typer.Option("--quiet")] = False,
    log_file: Annotated[Path | None, typer.Option("--log-file")] = None,
    version: Annotated[bool, typer.Option("--version", help="Print version and exit.")] = False,
) -> None:
    configure(verbose=verbose, quiet=quiet, log_file=log_file)
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)


def _parse_modules(modules: str) -> tuple[str, ...]:
    parsed = tuple(m.strip() for m in modules.split(",") if m.strip())
    for m in parsed:
        if m not in config.ALL_MODULES:
            raise UserError(f"Unknown module {m!r}. Valid: {', '.join(config.ALL_MODULES)}")
    return parsed or ("core",)


def _resolve_dump_dir(
    mirror: str,
    *,
    date: str | None,
    latest: bool,
    yes: bool,
) -> DumpDirectory:
    if date:
        return build_dated_dir(mirror, date)
    if latest:
        return resolve_latest(mirror)
    if yes:
        return resolve_latest(mirror)
    import questionary

    dirs = list_dated_dirs(mirror, limit=15)
    if not dirs:
        raise UserError(f"No dated dumps found at {mirror}")
    choice = questionary.select(
        "Select a dump directory:",
        choices=[d.name for d in dirs],
    ).ask()
    if choice is None:
        raise UserError("No selection made.")
    return next(d for d in dirs if d.name == choice)


def _workdir_for(settings_workdir: Path | None, dump: DumpDirectory) -> Path:
    base = settings_workdir or config.default_workdir()
    return base / dump.name


# ----------------------------------------------------------------- list-dumps


@app.command("list-dumps")
def list_dumps(
    mirror: MirrorOption = config.DEFAULT_MIRROR,
    limit: Annotated[int, typer.Option("--limit")] = 20,
) -> None:
    """List dated dump directories available on the mirror."""
    with _handle_errors():
        dirs = list_dated_dirs(mirror, limit=limit)
        if not dirs:
            typer.echo("(no dumps found)")
            return
        for d in dirs:
            typer.echo(f"{d.name}  {d.url}")


# -------------------------------------------------------------------- download


@app.command("download")
def download(
    mirror: MirrorOption = config.DEFAULT_MIRROR,
    modules: ModulesOption = "core",
    date: Annotated[
        str | None,
        typer.Option("--date", help="Dated dir, e.g. 20260408-002212"),
    ] = None,
    latest: Annotated[bool, typer.Option("--latest")] = False,
    dump_dir: Annotated[
        Path | None,
        typer.Option("--dump-dir", help="Local directory that already holds the archives."),
    ] = None,
    workdir: WorkdirOption = None,
    verify_flag: Annotated[bool, typer.Option("--verify/--no-verify")] = True,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Download the selected archives from the mirror."""
    with _handle_errors():
        mods = _parse_modules(modules)
        if dump_dir is not None:
            typer.echo(f"Using local dump dir: {dump_dir}")
            return
        chosen = _resolve_dump_dir(mirror, date=date, latest=latest, yes=yes)
        dest = _workdir_for(workdir, chosen)
        typer.echo(f"Downloading to {dest}")
        checksums = dl.fetch_checksums(chosen)
        with progress_session():
            for archive_name in manifest.archives_for(mods):
                dl.download_archive(
                    chosen, archive_name, dest, checksums=checksums, verify=verify_flag
                )
        typer.echo("Done.")


# ---------------------------------------------------------------------- schema


@schema_app.command("create")
def schema_create(
    db: DbOption = None,
    ref: RefOption = config.DEFAULT_SQL_REF,
    modules: ModulesOption = "core",
    phase: Annotated[Phase, typer.Option("--phase")] = Phase.ALL,
) -> None:
    """Fetch admin/sql/*.sql at <ref> and apply them to the target DB."""
    with _handle_errors():
        mods = _parse_modules(modules)
        sha = github.resolve_ref(ref)
        with connect(db) as conn, progress_session():
            orch = Orchestrator(conn, sha=sha, modules=mods)
            orch.run(phase)
        typer.echo(f"Schema phase {phase.value} complete (ref {ref} → {sha[:12]}).")


# ---------------------------------------------------------------------- import


@app.command("import")
def import_(
    db: DbOption = None,
    dump_dir: Annotated[
        Path,
        typer.Option("--dump-dir", help="Local directory containing the .tar.bz2 archives."),
    ] = ...,  # type: ignore[assignment]
    modules: ModulesOption = "core",
    force: Annotated[bool, typer.Option("--force-reimport")] = False,
) -> None:
    """Stream the TSVs from each archive into COPY FROM STDIN."""
    with _handle_errors():
        mods = _parse_modules(modules)
        with connect(db) as conn, progress_session():
            for archive_name in manifest.archives_for(mods):
                archive_path = dump_dir / archive_name
                if not archive_path.exists():
                    raise UserError(f"Archive not found: {archive_path}")
                import_archive(conn, archive_path, force=force)
        typer.echo("Import complete.")


# ------------------------------------------------------------------------ run


@app.command("run")
def run(
    db: DbOption = None,
    mirror: MirrorOption = config.DEFAULT_MIRROR,
    ref: RefOption = config.DEFAULT_SQL_REF,
    modules: ModulesOption = "core",
    date: Annotated[str | None, typer.Option("--date")] = None,
    latest: Annotated[bool, typer.Option("--latest")] = False,
    dump_dir: Annotated[Path | None, typer.Option("--dump-dir")] = None,
    workdir: WorkdirOption = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """End-to-end: list/pick → download → schema pre → import → schema post."""
    with _handle_errors():
        mods = _parse_modules(modules)
        sha = github.resolve_ref(ref)
        if dump_dir is None:
            chosen = _resolve_dump_dir(mirror, date=date, latest=latest, yes=yes)
            dump_dir = _workdir_for(workdir, chosen)
            checksums = dl.fetch_checksums(chosen)
            with progress_session():
                for archive_name in manifest.archives_for(mods):
                    dl.download_archive(chosen, archive_name, dump_dir, checksums=checksums)
        with connect(db) as conn, progress_session():
            orch = Orchestrator(conn, sha=sha, modules=mods)
            orch.run_pre_import()
            for archive_name in manifest.archives_for(mods):
                import_archive(conn, dump_dir / archive_name)
            orch.run_post_import()
        typer.echo("All done.")


# ---------------------------------------------------------------------- verify


@app.command("verify")
def verify_cmd(
    dump_dir: Annotated[Path, typer.Option("--dump-dir")] = ...,  # type: ignore[assignment]
    modules: ModulesOption = "core",
) -> None:
    """Print SCHEMA_SEQUENCE + REPLICATION_SEQUENCE from each archive."""
    with _handle_errors():
        mods = _parse_modules(modules)
        for archive_name in manifest.archives_for(mods):
            archive_path = dump_dir / archive_name
            if not archive_path.exists():
                typer.echo(f"{archive_name}: MISSING")
                continue
            seq = verify.read_schema_sequence(archive_path)
            rep = verify.read_replication_sequence(archive_path)
            typer.echo(f"{archive_name}: schema_seq={seq} replication_seq={rep}")


# ----------------------------------------------------------------------- clean


@app.command("clean")
def clean(
    workdir: WorkdirOption = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Remove cached downloads."""
    with _handle_errors():
        target = workdir or config.default_workdir()
        if not target.exists():
            typer.echo(f"{target} does not exist.")
            return
        if not yes and not typer.confirm(f"Delete {target}?"):
            raise typer.Exit(0)
        import shutil

        shutil.rmtree(target)
        typer.echo(f"Deleted {target}")


# -------------------------------------------------------------- error wrapping


@contextmanager
def _handle_errors() -> Iterator[None]:
    try:
        yield
    except MBSetupError as exc:
        get_console().print(f"[bold red]Error:[/] {exc}")
        sys.exit(exc.exit_code)
    except KeyboardInterrupt:
        get_console().print("[yellow]Interrupted.[/]")
        sys.exit(130)
