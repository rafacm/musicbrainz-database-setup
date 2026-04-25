"""Tests for the phase banner/footer helper.

The banner is printed via ``Console.rule`` to stderr, and the footer is a
single ``log.info`` line emitted by the ``phase_section`` context manager
itself. These assertions pin the visible contract: banner on entry, footer
on success, no footer on exception.
"""

from __future__ import annotations

import logging

import pytest

from musicbrainz_database_setup import logging as mbs_logging
from musicbrainz_database_setup.ui.phases import (
    PHASE_ORDER,
    RunPhase,
    format_elapsed,
    phase_section,
)


@pytest.fixture
def fresh_console_and_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the cached Console and root logger so capsys sees the output.

    See tests/unit/test_cli.py for the same pattern — the singleton Console
    binds to ``sys.stderr`` at construction time, so each test that uses
    capsys must rebuild it under the captured stderr.
    """
    monkeypatch.setattr(mbs_logging, "_console", None)
    root = logging.getLogger()
    original_level = root.level
    original_handlers = root.handlers[:]
    yield
    root.setLevel(original_level)
    root.handlers = original_handlers


def test_phase_order_lists_all_runphase_members() -> None:
    assert tuple(PHASE_ORDER) == (
        RunPhase.MIRROR,
        RunPhase.DOWNLOAD,
        RunPhase.SCHEMA_PRE,
        RunPhase.IMPORT,
        RunPhase.SCHEMA_POST,
    )
    assert set(PHASE_ORDER) == set(RunPhase)


def test_format_elapsed_under_a_minute() -> None:
    assert format_elapsed(0.05) == "0.1s"
    assert format_elapsed(12.34) == "12.3s"
    assert format_elapsed(59.9) == "59.9s"


def test_format_elapsed_minute_or_more() -> None:
    assert format_elapsed(60) == "1:00"
    assert format_elapsed(125) == "2:05"
    assert format_elapsed(3599) == "59:59"


def test_phase_section_emits_banner_and_footer_on_success(
    fresh_console_and_level: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging.basicConfig(level=logging.INFO, force=True)
    with phase_section(RunPhase.SCHEMA_PRE):
        pass

    err = capsys.readouterr().err
    # Banner: position in PHASE_ORDER is 3 (1-indexed) of 5.
    assert "Phase 3/5" in err
    assert "Schema (pre)" in err
    # Footer with elapsed time.
    assert "✓ Schema (pre) ·" in err


def test_phase_section_emits_no_footer_on_exception(
    fresh_console_and_level: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging.basicConfig(level=logging.INFO, force=True)
    with pytest.raises(RuntimeError), phase_section(RunPhase.IMPORT):
        raise RuntimeError("boom")

    err = capsys.readouterr().err
    # Banner still appears so the user sees which phase blew up …
    assert "Phase 4/5" in err
    assert "Import" in err
    # … but the success footer must not.
    assert "✓ Import" not in err
