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
    MIRROR = "Mirror"
    DOWNLOAD = "Download"
    SCHEMA_PRE = "Schema (pre)"
    IMPORT = "Import"
    SCHEMA_POST = "Schema (post)"


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
    log.info("✓ %s · %s", phase.value, format_elapsed(time.monotonic() - start))
