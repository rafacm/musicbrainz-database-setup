from unittest.mock import Mock

from musicbrainz_database_setup.schema.psql import _psql_env


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
