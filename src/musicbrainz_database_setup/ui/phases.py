"""Top-level pipeline phases and the banner/footer they emit.

The end-to-end ``run`` command moves through five phases in a fixed order;
standalone subcommands map to the relevant subset. ``phase_section`` is the
single place that emits a phase banner on entry and a one-line footer on
success, so output looks consistent whether the user runs the whole pipeline
or a single subcommand.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum

from musicbrainz_database_setup.logging import get_console

log = logging.getLogger(__name__)


class RunPhase(StrEnum):
    MIRROR = "Locate dump"
    DOWNLOAD = "Download"
    SCHEMA_PRE = "Schema setup"
    IMPORT = "Import tables"
    SCHEMA_POST = "Schema finalize"


PHASE_ORDER: tuple[RunPhase, ...] = (
    RunPhase.MIRROR,
    RunPhase.DOWNLOAD,
    RunPhase.SCHEMA_PRE,
    RunPhase.IMPORT,
    RunPhase.SCHEMA_POST,
)


def format_elapsed(seconds: float) -> str:
    """Render an elapsed duration: ``0.1s`` under a minute, ``M:SS`` under an
    hour, ``H:MM:SS`` from one hour up. Multi-hour rendering matters for the
    end-of-run summary on a full multi-module import.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_size(num_bytes: float) -> str:
    """Render a byte count in binary units (KiB / MiB / GiB / TiB)."""
    n = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


@contextmanager
def phase_section(
    phase: RunPhase,
    *,
    total_phases: int = len(PHASE_ORDER),
) -> Iterator[None]:
    """Emit a banner on entry and a ``✓ <phase> · <elapsed>`` footer on success.

    On exception, no footer is printed — the banner already in scrollback
    points the reader at the failing phase, and ``cli._handle_errors`` is
    responsible for the actual error rendering.

    Banner uses Homebrew's ``==>`` prefix style rather than a full-width rule
    so phase markers read as part of the log stream and don't depend on
    terminal width.
    """
    index = PHASE_ORDER.index(phase) + 1
    console = get_console()
    console.print(
        f"[bold blue]==>[/] [bold]Phase {index}/{total_phases} · {phase.value}[/]"
    )

    start = time.monotonic()
    yield
    # Past-tense "complete" suffix uniform across all phases keeps the footer
    # grammatical regardless of whether the label itself is a verb ("Download"),
    # noun ("Schema setup"), or imperative phrase ("Locate dump") — see
    # https://evilmartians.com/chronicles/cli-ux-best-practices-3-patterns-for-improving-progress-displays
    log.info(
        "✓ %s complete · %s",
        phase.value,
        format_elapsed(time.monotonic() - start),
    )


@contextmanager
def run_summary(label: str = "Run complete") -> Iterator[None]:
    """Time a top-level command and emit a brew-style summary line on success.

    Renders ``==> <label> · <elapsed>`` to the shared stderr Console *only* on
    clean exit. On exception the summary is suppressed — ``cli._handle_errors``
    owns the error rendering and a "Run complete" line after a failed run
    would mislead.
    """
    start = time.monotonic()
    yield
    elapsed = format_elapsed(time.monotonic() - start)
    get_console().print(f"[bold blue]==>[/] [bold]{label} · {elapsed}[/]")
