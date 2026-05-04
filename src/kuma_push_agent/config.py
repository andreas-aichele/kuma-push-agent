"""Configuration models for kuma-push-agent."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SSHConfig(BaseModel):
    """SSH connection configuration."""

    host: str
    port: int = 22
    username: str
    private_key_path: str
    connect_timeout_seconds: int = 5
    keepalive_seconds: int = 30


class MariaDBConfig(BaseModel):
    """MariaDB connection and query configuration."""

    host: str = "127.0.0.1"
    port: int = 3306
    username: str
    password_env: str
    database: str
    query: str = "SELECT 1;"
    expected_result: str = "1"


class CheckConfig(BaseModel):
    """Configuration for a single check."""

    name: str
    type: Literal["mariadb_via_ssh"] = "mariadb_via_ssh"
    interval_seconds: int = 60
    timeout_seconds: int = 10
    uptime_kuma_push_url: str
    ssh: SSHConfig
    mariadb: MariaDBConfig


class AgentConfig(BaseModel):
    """Top-level agent configuration."""

    checks: list[CheckConfig] = Field(default_factory=list)


def load_config(path: str | Path) -> AgentConfig:
    """Load and validate agent configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise ValueError(f"Config file is empty: {path}")

    return AgentConfig.model_validate(raw)
