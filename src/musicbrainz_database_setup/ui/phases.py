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
    """Render an elapsed duration: ``0.1s`` under a minute, ``M:SS`` above."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(round(seconds)), 60)
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
    """
    index = PHASE_ORDER.index(phase) + 1
    console = get_console()
    console.rule(f"Phase {index}/{total_phases} · {phase.value}", style="bold cyan")

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
