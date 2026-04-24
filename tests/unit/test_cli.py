"""Regression tests for `cli._handle_errors` verbose-vs-default behaviour.

The default path prints a single red `Error:` line and exits with
`MBSetupError.exit_code`. The verbose path (root logger at `DEBUG`) adds a
Rich traceback with the `__cause__` chain and still exits with the same
code. These tests pin both contracts because the behaviour hinges on global
logging state and is easy to regress.
"""

from __future__ import annotations

import logging

import pytest

from musicbrainz_database_setup import logging as mbs_logging
from musicbrainz_database_setup.cli import _handle_errors
from musicbrainz_database_setup.errors import ExitCode, NetworkError


@pytest.fixture
def fresh_console_and_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the cached Rich `Console` and root logger level per test.

    `logging.get_console()` caches a module-level singleton bound to `sys.stderr`
    at construction time. Without this reset, a Console built in an earlier
    test (or at import time) keeps a reference to the pre-capsys stderr, and
    the traceback output never reaches ``capsys.readouterr().err``.
    """
    monkeypatch.setattr(mbs_logging, "_console", None)
    root = logging.getLogger()
    original_level = root.level
    yield
    root.setLevel(original_level)


def test_handle_errors_prints_single_line_at_info_level(
    fresh_console_and_level: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging.getLogger().setLevel(logging.INFO)

    with pytest.raises(SystemExit) as excinfo, _handle_errors():
        raise NetworkError("boom")

    assert excinfo.value.code == ExitCode.NETWORK
    err = capsys.readouterr().err
    assert "Error:" in err
    assert "boom" in err
    assert "Traceback" not in err


def test_handle_errors_prints_traceback_at_debug_level(
    fresh_console_and_level: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging.getLogger().setLevel(logging.DEBUG)

    with pytest.raises(SystemExit) as excinfo, _handle_errors():
        try:
            raise ValueError("inner cause")
        except ValueError as inner:
            raise NetworkError("boom") from inner

    assert excinfo.value.code == ExitCode.NETWORK
    err = capsys.readouterr().err
    assert "Error:" in err
    assert "boom" in err
    assert "Traceback" in err
    # The `from` chain must render so diagnostics include the real cause.
    assert "inner cause" in err
