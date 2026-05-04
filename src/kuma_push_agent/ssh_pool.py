"""Thread-safe SSH connection pool keyed by (host, port, username, key_path)."""

from __future__ import annotations

import logging
import threading
from typing import NamedTuple

import paramiko

_logger = logging.getLogger(__name__)


class SSHKey(NamedTuple):
    """Hashable key identifying a unique SSH connection target."""

    host: str
    port: int
    username: str
    private_key_path: str


def _load_private_key(key_path: str) -> paramiko.PKey:
    """Try loading the private key as RSA, Ed25519, ECDSA, or DSS."""
    for key_class in (
        paramiko.RSAKey,
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.DSSKey,
    ):
        try:
            return key_class.from_private_key_file(key_path)
        except paramiko.SSHException:
            continue
    raise RuntimeError(f"Unable to load private key from {key_path!r}")


class SSHPool:
    """Thread-safe pool of Paramiko SSH clients reused across checks."""

    def __init__(self) -> None:
        self._clients: dict[SSHKey, paramiko.SSHClient] = {}
        self._lock = threading.Lock()

    def _is_alive(self, client: paramiko.SSHClient) -> bool:
        """Return True if the SSH transport is active and responsive."""
        try:
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                return False
            transport.send_ignore()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _setup_host_keys(self, client: paramiko.SSHClient, host: str) -> None:
        """Load system known_hosts; warn and fall back to AutoAddPolicy if host unknown."""
        try:
            client.load_system_host_keys()
        except Exception:  # noqa: BLE001
            pass

        if client.get_host_keys().lookup(host) is None:
            _logger.warning(
                "No known_hosts entry for %s; falling back to AutoAddPolicy. "
                "Add the host key to known_hosts for production deployments.",
                host,
            )
            # AutoAddPolicy is used only when the host has no known_hosts entry.
            # A warning is logged above. For strict security, mount a known_hosts
            # file so the else branch (RejectPolicy) is taken instead.
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

    def _connect(self, key: SSHKey, connect_timeout: int, keepalive: int) -> paramiko.SSHClient:
        """Create and return a new authenticated SSH client."""
        client = paramiko.SSHClient()
        self._setup_host_keys(client, key.host)

        try:
            pkey = _load_private_key(key.private_key_path)
        except RuntimeError as exc:
            raise paramiko.SSHException(str(exc)) from exc

        client.connect(
            hostname=key.host,
            port=key.port,
            username=key.username,
            pkey=pkey,
            timeout=connect_timeout,
            allow_agent=False,
            look_for_keys=False,
        )

        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(keepalive)

        _logger.debug(
            "SSH connection established: %s@%s:%d",
            key.username,
            key.host,
            key.port,
        )
        return client

    def get_client(
        self,
        key: SSHKey,
        connect_timeout: int,
        keepalive: int,
    ) -> paramiko.SSHClient:
        """Return an active SSH client for *key*, reconnecting if the connection is stale."""
        with self._lock:
            client = self._clients.get(key)
            if client is not None and self._is_alive(client):
                return client

            if client is not None:
                _logger.debug("Closing stale SSH connection to %s:%d", key.host, key.port)
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

            client = self._connect(key, connect_timeout, keepalive)
            self._clients[key] = client
            return client

    def invalidate(self, key: SSHKey) -> None:
        """Remove and close the SSH connection for *key*, forcing a reconnect next time."""
        with self._lock:
            client = self._clients.pop(key, None)
            if client is not None:
                _logger.debug("Invalidating SSH connection to %s:%d", key.host, key.port)
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

    def close_all(self) -> None:
        """Close every SSH connection in the pool."""
        with self._lock:
            for key, client in list(self._clients.items()):
                _logger.debug("Closing SSH connection to %s:%d", key.host, key.port)
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
            self._clients.clear()


_pool: SSHPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> SSHPool:
    """Return the process-wide SSH pool singleton."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = SSHPool()
    return _pool
