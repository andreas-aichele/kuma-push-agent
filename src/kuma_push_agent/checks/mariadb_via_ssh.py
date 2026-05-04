"""MariaDB health check executed over a Paramiko SSH direct-tcpip channel."""

from __future__ import annotations

import logging
import os
import time

import paramiko
import pymysql
import pymysql.err

from kuma_push_agent.checks.base import BaseCheck, CheckResult
from kuma_push_agent.config import CheckConfig
from kuma_push_agent.ssh_pool import SSHKey, get_pool

_logger = logging.getLogger(__name__)


class MariaDBViaSSHCheck(BaseCheck):
    """Connect to MariaDB through an SSH tunnel and run a validation query."""

    def __init__(self, cfg: CheckConfig) -> None:
        self._cfg = cfg
        self._ssh = cfg.ssh
        self._db = cfg.mariadb

    def run(self) -> CheckResult:
        """Run the check and return a :class:`CheckResult`."""
        start = time.monotonic()

        password = os.environ.get(self._db.password_env)
        if password is None:
            return CheckResult(
                ok=False,
                message=f"Environment variable '{self._db.password_env}' is not set",
            )

        ssh_key = SSHKey(
            host=self._ssh.host,
            port=self._ssh.port,
            username=self._ssh.username,
            private_key_path=self._ssh.private_key_path,
        )
        pool = get_pool()

        # Try up to 2 times to handle a stale pooled connection.
        for attempt in range(2):
            try:
                client = pool.get_client(
                    ssh_key,
                    connect_timeout=self._ssh.connect_timeout_seconds,
                    keepalive=self._ssh.keepalive_seconds,
                )
                transport = client.get_transport()
                channel = transport.open_channel(
                    "direct-tcpip",
                    (self._db.host, self._db.port),
                    ("127.0.0.1", 0),
                    timeout=self._cfg.timeout_seconds,
                )
                break
            except paramiko.AuthenticationException:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return CheckResult(
                    ok=False,
                    message="SSH authentication failed",
                    duration_ms=elapsed_ms,
                )
            except (paramiko.SSHException, OSError):
                pool.invalidate(ssh_key)
                if attempt == 1:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    return CheckResult(
                        ok=False,
                        message="SSH connection failed",
                        duration_ms=elapsed_ms,
                    )
        else:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CheckResult(
                ok=False,
                message="SSH connection failed",
                duration_ms=elapsed_ms,
            )

        db_conn = None
        try:
            db_conn = pymysql.connect(
                host=self._db.host,
                port=self._db.port,
                user=self._db.username,
                password=password,
                database=self._db.database,
                defer_connect=True,
                connect_timeout=self._cfg.timeout_seconds,
                read_timeout=self._cfg.timeout_seconds,
                write_timeout=self._cfg.timeout_seconds,
            )
            db_conn.connect(sock=channel)

            with db_conn.cursor() as cursor:
                cursor.execute(self._db.query)
                rows = cursor.fetchall()

            elapsed_ms = int((time.monotonic() - start) * 1000)

            if not rows:
                return CheckResult(
                    ok=False,
                    message="Query returned no rows",
                    duration_ms=elapsed_ms,
                )

            actual = str(rows[0][0]).strip()
            expected = self._db.expected_result.strip()

            if actual != expected:
                return CheckResult(
                    ok=False,
                    message=(f"Invalid query result: expected={expected!r} got={actual[:100]!r}"),
                    duration_ms=elapsed_ms,
                )

            return CheckResult(ok=True, message="OK", duration_ms=elapsed_ms)

        except pymysql.err.OperationalError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            err_code = exc.args[0] if exc.args else 0
            if err_code in (1045, 1044, 1043):
                return CheckResult(
                    ok=False,
                    message="MariaDB authentication failed",
                    duration_ms=elapsed_ms,
                )
            if err_code == 1049:
                return CheckResult(
                    ok=False,
                    message=f"MariaDB unknown database '{self._db.database}'",
                    duration_ms=elapsed_ms,
                )
            return CheckResult(
                ok=False,
                message="MariaDB connection failed",
                duration_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CheckResult(
                ok=False,
                message=f"Check failed: {type(exc).__name__}",
                duration_ms=elapsed_ms,
            )
        finally:
            if db_conn is not None:
                try:
                    db_conn.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                channel.close()
            except Exception:  # noqa: BLE001
                pass
