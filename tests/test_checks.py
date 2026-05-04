"""Tests for check implementations."""

from __future__ import annotations

import paramiko
import pymysql.err
import pytest

from kuma_push_agent.checks.base import CheckResult
from kuma_push_agent.checks.mariadb_via_ssh import MariaDBViaSSHCheck
from kuma_push_agent.config import CheckConfig, MariaDBConfig, SSHConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cfg(
    *,
    password_env: str = "TEST_DB_PASSWORD",
    expected_result: str = "1",
    query: str = "SELECT 1;",
) -> CheckConfig:
    return CheckConfig(
        name="test_check",
        uptime_kuma_push_url="https://kuma.example.com/api/push/token",
        ssh=SSHConfig(
            host="example.com",
            port=22,
            username="monitor",
            private_key_path="/run/secrets/ssh_key",
            connect_timeout_seconds=5,
            keepalive_seconds=30,
        ),
        mariadb=MariaDBConfig(
            username="monitor",
            password_env=password_env,
            database="testdb",
            query=query,
            expected_result=expected_result,
        ),
    )


def _setup_ssh(mocker: pytest.MonkeyPatch):
    """Patch get_pool and return (mock_pool, mock_client, mock_transport, mock_channel)."""
    mock_pool = mocker.Mock()
    mock_client = mocker.Mock()
    mock_transport = mocker.Mock()
    mock_channel = mocker.Mock()

    mock_pool.get_client.return_value = mock_client
    mock_client.get_transport.return_value = mock_transport
    mock_transport.open_channel.return_value = mock_channel

    mocker.patch(
        "kuma_push_agent.checks.mariadb_via_ssh.get_pool",
        return_value=mock_pool,
    )
    return mock_pool, mock_client, mock_transport, mock_channel


def _setup_db_cursor(mocker: pytest.MonkeyPatch, rows: list):
    """Return (mock_conn, mock_cursor) with fetchall configured."""
    mock_conn = mocker.MagicMock()
    mock_cursor = mocker.MagicMock()
    mock_cursor.__enter__ = mocker.Mock(return_value=mock_cursor)
    mock_cursor.__exit__ = mocker.Mock(return_value=False)
    mock_cursor.fetchall.return_value = rows
    mock_conn.cursor.return_value = mock_cursor
    mocker.patch("pymysql.connect", return_value=mock_conn)
    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


def test_check_result_ok_defaults() -> None:
    result = CheckResult(ok=True, message="OK")
    assert result.ok is True
    assert result.message == "OK"
    assert result.duration_ms == 0


def test_check_result_failure() -> None:
    result = CheckResult(ok=False, message="Something failed", duration_ms=123)
    assert result.ok is False
    assert result.duration_ms == 123


# ---------------------------------------------------------------------------
# MariaDBViaSSHCheck — success path
# ---------------------------------------------------------------------------


def test_success(mocker: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _, _, _, mock_channel = _setup_ssh(mocker)
    mock_conn, _ = _setup_db_cursor(mocker, [("1",)])

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is True
    assert result.message == "OK"
    assert result.duration_ms >= 0
    mock_conn.connect.assert_called_once_with(sock=mock_channel)


def test_success_custom_query_and_expected(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    _setup_db_cursor(mocker, [("42",)])

    result = MariaDBViaSSHCheck(
        _make_cfg(query="SELECT COUNT(*) FROM users;", expected_result="42")
    ).run()

    assert result.ok is True


# ---------------------------------------------------------------------------
# MariaDBViaSSHCheck — error paths
# ---------------------------------------------------------------------------


def test_missing_env_variable(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DB_PASSWORD", raising=False)
    mocker.patch("kuma_push_agent.checks.mariadb_via_ssh.get_pool")

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert "TEST_DB_PASSWORD" in result.message
    assert "not set" in result.message


def test_ssh_auth_failure(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    mock_pool = mocker.Mock()
    mock_pool.get_client.side_effect = paramiko.AuthenticationException()
    mocker.patch(
        "kuma_push_agent.checks.mariadb_via_ssh.get_pool",
        return_value=mock_pool,
    )

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert result.message == "SSH authentication failed"


def test_ssh_connection_failure_both_attempts(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    mock_pool = mocker.Mock()
    mock_pool.get_client.side_effect = paramiko.SSHException("connection refused")
    mocker.patch(
        "kuma_push_agent.checks.mariadb_via_ssh.get_pool",
        return_value=mock_pool,
    )

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert result.message == "SSH connection failed"
    assert mock_pool.invalidate.call_count == 2


def test_ssh_connection_failure_second_attempt(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First attempt stale, second attempt fails — should return SSH connection failed."""
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    mock_pool = mocker.Mock()

    mock_pool.get_client.side_effect = OSError("reset by peer")
    mocker.patch(
        "kuma_push_agent.checks.mariadb_via_ssh.get_pool",
        return_value=mock_pool,
    )

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert result.message == "SSH connection failed"


def test_mariadb_connection_failure(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    mock_conn = mocker.MagicMock()
    mock_conn.connect.side_effect = pymysql.err.OperationalError(2003, "Connection refused")
    mocker.patch("pymysql.connect", return_value=mock_conn)

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert result.message == "MariaDB connection failed"


def test_mariadb_auth_failure(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "wrongpassword")
    _setup_ssh(mocker)
    mock_conn = mocker.MagicMock()
    mock_conn.connect.side_effect = pymysql.err.OperationalError(1045, "Access denied")
    mocker.patch("pymysql.connect", return_value=mock_conn)

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert result.message == "MariaDB authentication failed"


def test_mariadb_unknown_database(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    mock_conn = mocker.MagicMock()
    mock_conn.connect.side_effect = pymysql.err.OperationalError(1049, "Unknown database")
    mocker.patch("pymysql.connect", return_value=mock_conn)

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert "testdb" in result.message


def test_invalid_query_result(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    _setup_db_cursor(mocker, [("2",)])

    result = MariaDBViaSSHCheck(_make_cfg(expected_result="1")).run()

    assert result.ok is False
    assert "expected=" in result.message
    assert "'1'" in result.message
    assert "'2'" in result.message


def test_query_returns_no_rows(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    _setup_db_cursor(mocker, [])

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert "no rows" in result.message.lower()


def test_unexpected_exception_caught(
    mocker: pytest.MonkeyPatch,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DB_PASSWORD", "secret")
    _setup_ssh(mocker)
    mock_conn = mocker.MagicMock()
    mock_conn.connect.side_effect = RuntimeError("unexpected")
    mocker.patch("pymysql.connect", return_value=mock_conn)

    result = MariaDBViaSSHCheck(_make_cfg()).run()

    assert result.ok is False
    assert "RuntimeError" in result.message
