# kuma-push-agent

[![CI](https://github.com/andreas-aichele/kuma-push-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/andreas-aichele/kuma-push-agent/actions/workflows/ci.yml)
[![Docker Image](https://ghcr-badge.egpl.dev/andreas-aichele/kuma-push-agent/latest_tag?trim=major&label=ghcr.io)](https://github.com/andreas-aichele/kuma-push-agent/pkgs/container/kuma-push-agent)

> A lightweight, Dockerized push monitoring agent for Uptime Kuma

## What Problem It Solves

Many databases and services live behind firewalls or NAT, reachable only over SSH. Uptime Kuma's
**push monitors** require the monitored service to periodically call a push URL — perfect when
Kuma cannot poll the target. `kuma-push-agent` bridges the gap: it runs inside your
infrastructure, reaches services through SSH tunnels, and pushes heartbeats to your Uptime Kuma
instance.

You can monitor a MariaDB instance on a remote server without:

- Exposing the database port to the internet
- Running agent software on the monitored server itself
- Leaking passwords into the process list

## Features

- 🔒 **Secure SSH tunnelling** — MariaDB connections travel over Paramiko `direct-tcpip` channels;
  no credentials appear in `ps` output
- 🔁 **SSH session reuse** — a thread-safe pool maintains one SSH connection per target host,
  shared across all checks
- ⚙️ **Pydantic v2 config** — strongly-typed YAML configuration with clear, actionable
  validation errors
- 📦 **Dockerized** — minimal Python 3.12 slim image; secrets injected via environment variables
  and Docker secrets
- 🔗 **Uptime Kuma push** — HTTP GET with automatic token masking in log output
- 📋 **APScheduler 3.x** — reliable interval scheduling; first run fires immediately on startup
- 🔑 **Multi-key-type** — RSA, Ed25519, ECDSA, and DSS SSH private keys all supported

## Docker Image

A pre-built image is published to the **GitHub Container Registry** on every push to `main`
and on every version tag:

```
ghcr.io/andreas-aichele/kuma-push-agent:latest
ghcr.io/andreas-aichele/kuma-push-agent:0.1.0   # pinned release
```

Pull the latest image directly — no build step required:

```bash
docker pull ghcr.io/andreas-aichele/kuma-push-agent:latest
```

The provided `docker-compose.yml` uses this image by default.
To build from source instead, replace the `image:` line with `build: .`.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      kuma-push-agent                         │
│                                                              │
│  main.py                                                     │
│    └─ AgentScheduler (APScheduler BackgroundScheduler)       │
│         └─ per-check interval job ──► _run_check_job()       │
│                                            │                 │
│                                    MariaDBViaSSHCheck.run()  │
│                                      │            │          │
│                               SSHPool            pymysql     │
│                            .get_client()      .connect(      │
│                                 │              sock=channel) │
│                         Paramiko SSH conn                    │
│                           └─ direct-tcpip ──► MariaDB port   │
│                                                              │
│  uptime_kuma.push() ──────────────────────► Kuma push URL    │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker ≥ 24 and Docker Compose v2 (`docker compose` — note: no hyphen)
- An Uptime Kuma instance with at least one **Push** monitor configured
- SSH access to the server hosting MariaDB

### 1. Create a working directory and download the config templates

No clone required — the image is pulled automatically by Docker Compose.
You only need the two template files:

```bash
mkdir kuma-push-agent && cd kuma-push-agent
mkdir -p secrets
# Download the config templates from the repository
curl -fsSL https://raw.githubusercontent.com/andreas-aichele/kuma-push-agent/main/config.example.yml -o config.example.yml
curl -fsSL https://raw.githubusercontent.com/andreas-aichele/kuma-push-agent/main/.env.example       -o .env.example
curl -fsSL https://raw.githubusercontent.com/andreas-aichele/kuma-push-agent/main/docker-compose.yml -o docker-compose.yml
```

### 2. Generate a dedicated SSH key

```bash
ssh-keygen -t ed25519 -f secrets/ssh_key -N "" -C "kuma-push-agent"
# Install the public key on the target server:
ssh-copy-id -i secrets/ssh_key.pub monitor@example.com
```

### 3. Add the target host to known_hosts

The agent uses strict host key verification and will refuse to connect to any host
not listed in `known_hosts`. Run this for **each** SSH host you will monitor:

```bash
ssh-keyscan -H example.com >> secrets/known_hosts
```

### 4. Create the Push monitor in Uptime Kuma

1. **Add Monitor → Push**
2. Set the **Heartbeat Interval** to match `interval_seconds` in your config (e.g., `60`)
3. Copy the generated push URL — you will paste it into `config.yml`

### 5. Configure the agent

```bash
cp config.example.yml config.yml
cp .env.example .env
```

Edit `config.yml` — fill in your SSH host, Uptime Kuma push URL, and MariaDB details:

```yaml
checks:
  - name: web_prod_db
    type: mariadb_via_ssh
    interval_seconds: 60
    timeout_seconds: 10
    uptime_kuma_push_url: "https://kuma.example.com/api/push/YOUR_TOKEN"
    ssh:
      host: "example.com"
      username: "monitor"
      private_key_path: "/run/secrets/ssh_key"
    mariadb:
      username: "monitor"
      password_env: "WEB_DB_PASSWORD"
      database: "web"
```

Set the MariaDB password in `.env`:

```
WEB_DB_PASSWORD=your-monitor-password
```

### 6. Start the agent

```bash
docker compose up -d       # pulls ghcr.io/andreas-aichele/kuma-push-agent:latest automatically
docker compose logs -f
```

Expected log output:

```
2024-01-15T10:30:00Z INFO  kuma_push_agent.main       kuma-push-agent v0.1.0 starting with 1 check(s)
2024-01-15T10:30:00Z INFO  kuma_push_agent.scheduler  Scheduled check 'web_prod_db' every 60s
2024-01-15T10:30:00Z INFO  kuma_push_agent.scheduler  Scheduler started with 1 job(s)
2024-01-15T10:30:01Z INFO  kuma_push_agent.scheduler  Check 'web_prod_db': ok=True msg=OK ping=312ms
2024-01-15T10:30:01Z INFO  kuma_push_agent.uptime_kuma Pushing to Uptime Kuma: https://kuma.example.com/api/push/*** status=up msg=OK ping=312ms
```

### Directory layout after setup

```
kuma-push-agent/
├── config.yml            ← your active configuration
├── .env                  ← MariaDB passwords
└── secrets/
    ├── ssh_key           ← SSH private key (never commit this)
    ├── ssh_key.pub       ← SSH public key (install on target server)
    └── known_hosts       ← target host fingerprints (ssh-keyscan output)
```

## Configuration Reference

### `config.yml`

```yaml
checks:
  - name: <string>               # Unique identifier — appears in all log lines
    type: mariadb_via_ssh        # Only supported type; more coming in roadmap
    interval_seconds: 60         # Push heartbeat every N seconds (match Kuma setting)
    timeout_seconds: 10          # Per-check deadline: SSH channel open + query execution
    uptime_kuma_push_url: <url>  # Full push URL copied from the Kuma monitor page

    ssh:
      host: <string>             # SSH server hostname or IP address
      port: 22                   # SSH port (default: 22)
      username: <string>         # SSH login username
      private_key_path: <path>   # Absolute path to the SSH private key file
      connect_timeout_seconds: 5 # TCP connect timeout in seconds (default: 5)
      keepalive_seconds: 30      # SSH keepalive interval in seconds (default: 30)

    mariadb:
      host: "127.0.0.1"          # MariaDB host as seen from the SSH server (default: 127.0.0.1)
      port: 3306                 # MariaDB port (default: 3306)
      username: <string>         # MariaDB login username
      password_env: <string>     # Name of the environment variable holding the password
      database: <string>         # Database to connect to
      query: "SELECT 1;"         # SQL query to execute (default: SELECT 1;)
      expected_result: "1"       # Expected string value of column 0, row 0 (default: "1")
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `LOG_LEVEL` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `<password_env>` | MariaDB password; name is set per-check via `password_env` | — |

## Uptime Kuma Setup

1. Open your Uptime Kuma dashboard → **Add New Monitor**
2. Select type **Push**
3. Set **Friendly Name** (e.g., `web_prod_db`)
4. Set **Heartbeat Interval** (e.g., `60` seconds — must match `interval_seconds`)
5. Copy the generated push URL (looks like `https://kuma.example.com/api/push/XXXXX`)
6. Paste it into `uptime_kuma_push_url` in `config.yml`
7. Save the monitor — it will show as **pending** until the first push arrives

## Security Recommendations

### Dedicated SSH user

```bash
# On the target server
adduser --disabled-password --gecos "" monitor
```

Restrict the user in `/etc/ssh/sshd_config`:

```
Match User monitor
    AllowTcpForwarding yes
    X11Forwarding no
    PermitTTY no
    ForceCommand /bin/false
```

### Dedicated MariaDB user

```sql
CREATE USER 'monitor'@'127.0.0.1' IDENTIFIED BY 'strong-random-password';
GRANT SELECT ON web.* TO 'monitor'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### SSH host key verification

The agent always uses `RejectPolicy` — it will never silently accept an unknown host key.
Add each target host's fingerprint to `secrets/known_hosts` before starting the agent
(see [Quick Start step 3](#3-add-the-target-host-to-known_hosts)):

```bash
ssh-keyscan -H example.com >> secrets/known_hosts
```

The `docker-compose.yml` already mounts this file at `/root/.ssh/known_hosts:ro` inside
the container.

### Docker secrets

The `docker-compose.yml` mounts the SSH private key via Docker Compose secrets at
`/run/secrets/ssh_key` inside the container — never pass it as an environment variable.

## SSH Session Reuse

`SSHPool` maintains one Paramiko SSH client per unique `(host, port, username, key_path)` tuple.
Connections are:

- **Reused** across all checks targeting the same SSH server
- **Validated** before each use (transport liveness probe + `send_ignore`)
- **Reconnected** automatically when a stale connection is detected (one retry per check run)
- **Kept alive** via SSH keepalive packets (default: every 30 seconds)

If you run 5 checks against the same SSH host, only **one** SSH connection is ever open.

## Logging Output Examples

```
2024-01-15T10:30:00Z INFO  kuma_push_agent.main       kuma-push-agent v0.1.0 starting with 2 check(s)
2024-01-15T10:30:00Z INFO  kuma_push_agent.scheduler  Scheduled check 'web_prod_db' every 60s
2024-01-15T10:30:00Z INFO  kuma_push_agent.scheduler  Scheduler started with 2 job(s)
2024-01-15T10:30:01Z INFO  kuma_push_agent.scheduler  Check 'web_prod_db': ok=True msg=OK ping=312ms
2024-01-15T10:30:01Z INFO  kuma_push_agent.uptime_kuma Pushing to Uptime Kuma: https://kuma.example.com/api/push/*** status=up msg=OK ping=312ms
2024-01-15T10:31:00Z INFO  kuma_push_agent.scheduler  Check 'web_prod_db': ok=False msg=SSH connection failed ping=5001ms
2024-01-15T10:31:00Z INFO  kuma_push_agent.uptime_kuma Pushing to Uptime Kuma: https://kuma.example.com/api/push/*** status=down msg=SSH+connection+failed ping=5001ms
```

## Roadmap

- [ ] PostgreSQL via SSH check
- [ ] Redis via SSH check
- [ ] HTTP/HTTPS reachability check
- [ ] Configurable `known_hosts` path via config
- [ ] Prometheus `/metrics` endpoint
- [ ] Multiple push URLs per check (fan-out to several Kuma monitors)
- [ ] Graceful config reload on `SIGHUP`

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Make your changes
5. Lint: `ruff check src/ tests/`
6. Format: `ruff format src/ tests/`
7. Test: `pytest tests/ -v`
8. Open a pull request — CI will run automatically

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.