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

    # httpx/httpcore log every request at INFO. At default verbosity each SQL
    # file fetch and every mirror/GitHub call would print "HTTP Request: GET
    # …" — cluttering the screen and burying the per-phase output. Promote
    # them to DEBUG so they only surface under ``-v``.
    http_level = logging.DEBUG if verbose else logging.WARNING
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(http_level)

    rich_handler = RichHandler(
        console=get_console(),
        show_time=False,
        show_path=False,
        show_level=False,
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

    return logging.getLogger("musicbrainz_database_setup")
