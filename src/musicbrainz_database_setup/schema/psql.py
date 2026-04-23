"""Shell out to ``psql`` to run upstream ``admin/sql/*.sql`` files.

These files are written for psql: each one begins with ``\\set
ON_ERROR_STOP 1`` and wraps its body in ``BEGIN; ... COMMIT;``. Handling
psql meta-commands and the file's own transaction scope via a Python
SQL driver would mean reimplementing a subset of psql. The upstream
``admin/InitDb.pl`` shells out to ``psql -f <file>`` for every SQL
file, and we do the same so behaviour matches byte-for-byte.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from psycopg import Connection

from musicbrainz_database_setup.errors import PrerequisiteMissing, SchemaError

log = logging.getLogger(__name__)


def ensure_psql_available() -> None:
    """Raise ``PrerequisiteMissing`` if ``psql`` is not on ``$PATH``."""
    if shutil.which("psql") is None:
        raise PrerequisiteMissing(
            "The `psql` client is required to apply the upstream "
            "admin/sql/*.sql files (which use psql meta-commands). "
            "Install it: `brew install libpq` on macOS, "
            "`apt install postgresql-client` on Debian/Ubuntu, "
            "or the equivalent on your distro."
        )


def _psql_env(conn: Connection) -> dict[str, str]:
    """Extract libpq env vars from a psycopg connection.

    We pass credentials to ``psql`` via environment variables (not
    command-line flags) so the password never shows up in ``ps``.
    """
    info = conn.info
    env = os.environ.copy()
    if info.host:
        env["PGHOST"] = info.host
    if info.port:
        env["PGPORT"] = str(info.port)
    if info.user:
        env["PGUSER"] = info.user
    if info.dbname:
        env["PGDATABASE"] = info.dbname
    if info.password:
        env["PGPASSWORD"] = info.password
    return env


def run_sql_file(conn: Connection, file_path: Path) -> None:
    """Execute ``file_path`` through ``psql``.

    Uses the connection's credentials (host, port, user, dbname,
    password) via env vars. Relies on ``psql``'s own handling of
    ``\\set ON_ERROR_STOP 1`` plus our belt-and-braces ``-v
    ON_ERROR_STOP=1`` to fail on the first SQL error. Stdout and
    stderr are captured and re-emitted at DEBUG / WARNING.
    """
    cmd = [
        "psql",
        "-X",  # ignore ~/.psqlrc
        "-q",  # quiet (suppress the chatty "CREATE EXTENSION" acknowledgements)
        "-v", "ON_ERROR_STOP=1",
        "-f", str(file_path),
    ]
    env = _psql_env(conn)
    log.debug("Invoking %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        log.debug("psql stdout: %s", result.stdout.rstrip())
    if result.returncode != 0:
        # psql prints the file + line number of the failing statement to stderr.
        raise SchemaError(
            f"psql failed applying {file_path.name} (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    if result.stderr.strip():
        log.warning("psql stderr: %s", result.stderr.rstrip())
