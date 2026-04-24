from unittest.mock import Mock

from musicbrainz_database_setup.schema.psql import _PGOPTIONS, _psql_env


def _mock_conn(password):
    conn = Mock()
    conn.info.host = "localhost"
    conn.info.port = 5432
    conn.info.user = "postgres"
    conn.info.dbname = "postgres"
    conn.info.password = password
    return conn


def test_psql_env_sets_pgpassword_when_url_has_password(monkeypatch):
    monkeypatch.delenv("PGPASSWORD", raising=False)
    env = _psql_env(_mock_conn("secret"))
    assert env["PGPASSWORD"] == "secret"
    assert env["PGHOST"] == "localhost"
    assert env["PGPORT"] == "5432"
    assert env["PGUSER"] == "postgres"
    assert env["PGDATABASE"] == "postgres"


def test_psql_env_preserves_inherited_pgpassword_when_url_has_none(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "inherited-secret")
    env = _psql_env(_mock_conn(None))
    assert env["PGPASSWORD"] == "inherited-secret"


def test_psql_env_omits_pgpassword_when_absent_everywhere(monkeypatch):
    monkeypatch.delenv("PGPASSWORD", raising=False)
    env = _psql_env(_mock_conn(None))
    assert "PGPASSWORD" not in env


def test_psql_env_pgoptions_includes_ddl_performance_knobs(monkeypatch):
    """PGOPTIONS must propagate the DDL tuning into every psql invocation.

    Without these, psql-driven post-import DDL (CreateIndexes.sql,
    CreateFKConstraints.sql, CreateConstraints.sql) runs on Postgres stock
    defaults — 64 MB maintenance_work_mem, synchronous_commit=on — which
    roughly doubles total import time. See CHANGELOG 2026-04-24.
    """
    monkeypatch.delenv("PGPASSWORD", raising=False)
    env = _psql_env(_mock_conn("secret"))
    opts = env["PGOPTIONS"]
    # search_path + quiet-notice preserved (upstream InitDb.pl parity)
    assert "search_path=musicbrainz,public" in opts
    assert "client_min_messages=WARNING" in opts
    # Performance knobs mirroring db.bulk_session()
    assert "synchronous_commit=off" in opts
    assert "maintenance_work_mem=2GB" in opts
    assert "work_mem=256MB" in opts
    assert "max_parallel_maintenance_workers=4" in opts
    assert "statement_timeout=0" in opts


def test_pgoptions_constant_matches_psql_env_output():
    """_PGOPTIONS constant and _psql_env()['PGOPTIONS'] stay in lockstep."""
    env = _psql_env(_mock_conn(None))
    assert env["PGOPTIONS"] == _PGOPTIONS
