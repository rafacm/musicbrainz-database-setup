from __future__ import annotations

import logging
import os
from pathlib import Path

from rich.console import Console
from rich.highlighter import Highlighter
from rich.logging import RichHandler
from rich.text import Text

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(stderr=True)
    return _console


def _reset_console() -> None:
    """Drop the cached Console so the next ``get_console()`` rebuilds it.

    Used when ``configure()`` learns about an env var (e.g. ``NO_COLOR``) that
    must be honoured at Console construction time.
    """
    global _console
    _console = None


class _CheckmarkHighlighter(Highlighter):
    """Render the leading ✓ on success log lines in bold green.

    Keeps the underlying log message string ASCII-friendly (no embedded Rich
    markup) so ``--log-file`` and any other downstream text consumer get the
    plain text.
    """

    def highlight(self, text: Text) -> None:
        plain = text.plain
        for index, char in enumerate(plain):
            if char == "✓":
                text.stylize("bold green", index, index + 1)


class _SeverityRichHandler(RichHandler):
    """``RichHandler`` that prefixes WARNING/ERROR records with a text label.

    clig.dev advises against printing log-level labels on routine output
    (``"Don't print log level labels (ERR, WARN, etc.) or extraneous
    contextual information, unless in verbose mode."``), but the convention
    in user-facing CLIs (``cargo``, ``npm``, ``pip``, ``brew``, ``gh``,
    ``terraform``) is to keep an explicit ``Warning:`` / ``Error:`` prefix
    on those specific levels — so severity stays readable when colour is
    stripped (``--no-color``, NO_COLOR, redirected stderr).

    INFO / DEBUG records pass through unchanged, matching the symbol-based
    markers (``==>``, ``✓``) we already use for routine progress.
    """

    def render_message(self, record: logging.LogRecord, message: str) -> Text:
        # Rich's type stubs declare the return as ConsoleRenderable, but the
        # implementation always returns Text — assert + cast keeps mypy happy
        # and surfaces any future Rich change loud and early.
        rendered = super().render_message(record, message)
        assert isinstance(rendered, Text)
        if record.levelno >= logging.ERROR:
            return Text.assemble(("Error: ", "bold red"), rendered)
        if record.levelno >= logging.WARNING:
            return Text.assemble(("Warning: ", "bold yellow"), rendered)
        return rendered


def configure(
    *,
    verbose: bool = False,
    quiet: bool = False,
    log_file: Path | None = None,
    no_color: bool = False,
) -> logging.Logger:
    # Respect ``--no-color``/``NO_COLOR`` *before* the Console is constructed:
    # Rich reads the env var once, at Console init. The env var must be set
    # first so the cached Console (rebuilt below) honours it.
    if no_color:
        os.environ["NO_COLOR"] = "1"
        _reset_console()

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

    rich_handler = _SeverityRichHandler(
        console=get_console(),
        show_time=False,
        show_path=False,
        show_level=False,
        markup=False,
        rich_tracebacks=True,
        highlighter=_CheckmarkHighlighter(),
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
