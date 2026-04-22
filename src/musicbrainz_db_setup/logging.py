from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(stderr=True)
    return _console


def configure(
    *, verbose: bool = False, quiet: bool = False, log_file: Path | None = None
) -> logging.Logger:
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    rich_handler = RichHandler(
        console=get_console(),
        show_time=False,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )
    rich_handler.setLevel(level)
    root.addHandler(rich_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(fh)

    return logging.getLogger("musicbrainz_db_setup")
