"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from kuma_push_agent.config import AgentConfig, load_config

VALID_YAML = """\
checks:
  - name: test_check
    type: mariadb_via_ssh
    interval_seconds: 60
    timeout_seconds: 10
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token123"
    ssh:
      host: "example.com"
      port: 22
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB_PASSWORD"
      database: "mydb"
"""


def test_valid_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yml"
    config_file.write_text(VALID_YAML)

    config = load_config(config_file)

    assert len(config.checks) == 1
    check = config.checks[0]
    assert check.name == "test_check"
    assert check.type == "mariadb_via_ssh"
    assert check.interval_seconds == 60
    assert check.timeout_seconds == 10
    assert check.ssh.host == "example.com"
    assert check.ssh.port == 22
    assert check.ssh.connect_timeout_seconds == 5  # default
    assert check.ssh.keepalive_seconds == 30  # default
    assert check.mariadb.host == "127.0.0.1"  # default
    assert check.mariadb.database == "mydb"
    assert check.mariadb.expected_result == "1"  # default
    assert check.mariadb.query == "SELECT 1;"  # default


def test_missing_required_name_raises(tmp_path: Path) -> None:
    yaml_content = """\
checks:
  - type: mariadb_via_ssh
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token"
    ssh:
      host: "example.com"
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB_PASSWORD"
      database: "mydb"
"""
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml_content)

    with pytest.raises(ValidationError):
        load_config(config_file)


def test_invalid_check_type_raises(tmp_path: Path) -> None:
    yaml_content = """\
checks:
  - name: bad_check
    type: invalid_type
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token"
    ssh:
      host: "example.com"
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB_PASSWORD"
      database: "mydb"
"""
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml_content)

    with pytest.raises(ValidationError):
        load_config(config_file)


def test_multiple_checks(tmp_path: Path) -> None:
    yaml_content = """\
checks:
  - name: check1
    type: mariadb_via_ssh
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token1"
    ssh:
      host: "server1.example.com"
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB1_PASSWORD"
      database: "db1"
  - name: check2
    type: mariadb_via_ssh
    interval_seconds: 120
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token2"
    ssh:
      host: "server2.example.com"
      username: "admin"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB2_PASSWORD"
      database: "db2"
      query: "SELECT COUNT(*) FROM users;"
      expected_result: "42"
"""
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml_content)

    config = load_config(config_file)

    assert len(config.checks) == 2
    assert config.checks[0].name == "check1"
    assert config.checks[1].name == "check2"
    assert config.checks[1].interval_seconds == 120
    assert config.checks[1].mariadb.expected_result == "42"
    assert config.checks[1].mariadb.query == "SELECT COUNT(*) FROM users;"


def test_file_not_found_raises() -> None:
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/config.yml")


def test_empty_config_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yml"
    config_file.write_text("")

    with pytest.raises(ValueError, match="empty"):
        load_config(config_file)


def test_agent_config_default_empty_checks() -> None:
    config = AgentConfig()
    assert config.checks == []


def test_ssh_defaults() -> None:
    config_file_content = """\
checks:
  - name: defaults_check
    uptime_kuma_push_url: "https://kuma.example.com/api/push/token"
    ssh:
      host: "example.com"
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "DB_PASSWORD"
      database: "mydb"
"""
    import io

    import yaml

    from kuma_push_agent.config import AgentConfig

    raw = yaml.safe_load(io.StringIO(config_file_content))
    config = AgentConfig.model_validate(raw)
    ssh = config.checks[0].ssh
    assert ssh.port == 22
    assert ssh.connect_timeout_seconds == 5
    assert ssh.keepalive_seconds == 30
