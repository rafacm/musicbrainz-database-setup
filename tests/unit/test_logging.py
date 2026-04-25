"""Tests for the logging configuration.

The configure() function is called once on every CLI invocation and silently
governs how chatty the output is. These tests pin the contracts that matter
to user-visible output: root level + the httpx/httpcore promotion to DEBUG.
"""

from __future__ import annotations

import logging

import pytest

from musicbrainz_database_setup.logging import configure


@pytest.fixture
def reset_loggers() -> None:
    """Snapshot + restore root + named-logger levels so tests don't leak."""
    root = logging.getLogger()
    original_root_level = root.level
    original_root_handlers = root.handlers[:]
    httpx = logging.getLogger("httpx")
    httpcore = logging.getLogger("httpcore")
    original_httpx_level = httpx.level
    original_httpcore_level = httpcore.level
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
