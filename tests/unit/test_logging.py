"""Tests for the logging configuration.

The configure() function is called once on every CLI invocation and silently
governs how chatty the output is. These tests pin the contracts that matter
to user-visible output: root level + the httpx/httpcore promotion to DEBUG +
the ``--no-color``/``NO_COLOR`` Console reset.
"""

from __future__ import annotations

import logging
import os

import pytest

from musicbrainz_database_setup import logging as mbs_logging
from musicbrainz_database_setup.logging import configure


@pytest.fixture
def reset_loggers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snapshot + restore root + named-logger levels so tests don't leak.

    Also resets the cached Console and the ``NO_COLOR`` env var so tests that
    flip ``--no-color`` don't poison subsequent ones.
    """
    root = logging.getLogger()
    original_root_level = root.level
    original_root_handlers = root.handlers[:]
    httpx = logging.getLogger("httpx")
    httpcore = logging.getLogger("httpcore")
    original_httpx_level = httpx.level
    original_httpcore_level = httpcore.level
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(mbs_logging, "_console", None)
    yield
    root.setLevel(original_root_level)
    root.handlers = original_root_handlers
    httpx.setLevel(original_httpx_level)
    httpcore.setLevel(original_httpcore_level)


def test_default_quiets_httpx_to_warning(reset_loggers: None) -> None:
    configure(verbose=False, quiet=False)

    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_verbose_lifts_httpx_to_debug(reset_loggers: None) -> None:
    configure(verbose=True, quiet=False)

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.DEBUG
    assert logging.getLogger("httpcore").level == logging.DEBUG


def test_quiet_keeps_httpx_at_warning(reset_loggers: None) -> None:
    configure(verbose=False, quiet=True)

    assert logging.getLogger().level == logging.WARNING
    # quiet still suppresses INFO chatter at root, and httpx stays at WARNING
    # — the user shouldn't see HTTP request lines either way.
    assert logging.getLogger("httpx").level == logging.WARNING


def test_no_color_flag_sets_env_and_disables_console_colour(
    reset_loggers: None,
) -> None:
    configure(verbose=False, quiet=False, no_color=True)

    # NO_COLOR is the conventional opt-out env var
    # (https://no-color.org/). Setting it before Console init is what
    # makes Rich actually drop colour output.
    assert os.environ.get("NO_COLOR") == "1"
    assert mbs_logging.get_console().no_color is True


def test_default_leaves_no_color_unset(reset_loggers: None) -> None:
    configure(verbose=False, quiet=False, no_color=False)

    assert "NO_COLOR" not in os.environ
    # Without --no-color the Console may still auto-disable colour because
    # capsys captures stderr (Rich treats a non-tty as no-colour). What we
    # care about is that we did not _force_ NO_COLOR on.
    assert mbs_logging.get_console().no_color is False
