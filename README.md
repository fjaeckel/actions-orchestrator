# actions-orchestrator

Run multiple GitHub Actions self-hosted runners on a single machine — one runner per repository. Designed for private GitHub accounts where runners can't be shared across repos.

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator                                               │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Runner #1    │  │ Runner #2    │  │ Runner #3    │ ...   │
│  │ owner/repo-a │  │ owner/repo-b │  │ owner/repo-c │      │
│  │ (pid 1234)   │  │ (pid 1235)   │  │ (pid 1236)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  Health monitor thread — auto-restarts crashed runners      │
└─────────────────────────────────────────────────────────────┘
```

Each runner:
- Lives in its own directory (`runners/<owner>-<repo>/`)
- Is registered independently with one GitHub repository
- Runs as its own process with isolated work directories
- Is monitored and auto-restarted if it crashes

## Quick start

### 1. Clone & install

```bash
git clone https://github.com/fjaeckel/actions-orchestrator.git
cd actions-orchestrator
python3 -m pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml`:

```yaml
github_pat: "ghp_your_personal_access_token"
runners_base: "./runners"

repositories:
  - owner: "your-username"
    repo: "repo-one"
  - owner: "your-username"
    repo: "repo-two"
    labels:
      - "docker"
```

The PAT needs the **`repo`** scope (classic token) or **Administration read/write** permission (fine-grained token) for each repository.

Alternatively, set `GITHUB_PAT` as an environment variable or in a `.env` file.

### 3. Run

```bash
# Setup only (download runner binary, configure all repos):
make setup

# Start all runners + health monitor (foreground, Ctrl+C to stop):
make start

# Or use the CLI directly:
python3 -m orchestrator start
```

## CLI commands

| Command | Description |
|----------------|----------------------------------------------|
| `setup` | Download runner binary, provision & configure |
| `start` | Start all runners + health monitor (blocks) |
| `stop` | Stop all running runner processes |
| `status` | Query GitHub API for registered runner status |
| `unregister` | Deregister all runners from GitHub |
| `destroy` | Unregister + delete all runner directories |

All commands accept `-c <path>` to specify a config file (default: `config.yaml`).

```bash
python3 -m orchestrator -c production.yaml start
```

## Directory layout

```
actions-orchestrator/
├── config.yaml.example     # Example configuration
├── config.yaml             # Your configuration (gitignored)
├── Makefile                 # Convenience targets
├── requirements.txt        # Python dependencies
├── scripts/
│   └── download-runner.sh  # Downloads GitHub Actions runner binary
├── orchestrator/
│   ├── __init__.py
│   ├── __main__.py         # python -m orchestrator entry point
│   ├── cli.py              # Argument parsing & subcommands
│   ├── config.py           # Configuration loading
│   ├── github_api.py       # GitHub API (registration tokens, etc.)
│   ├── orchestrator.py     # Fleet management & health monitoring
│   └── runner.py           # Single runner instance lifecycle
├── _runner_template/       # Downloaded runner binary (gitignored)
└── runners/                # Per-repo runner directories (gitignored)
    ├── you-repo-one/
    │   ├── run.sh
    │   ├── config.sh
    │   ├── _work/
    │   └── ...
    └── you-repo-two/
        └── ...
```

## Configuration reference

### config.yaml

| Key | Type | Default | Description |
|---|---|---|---|
| `github_pat` | string | — | GitHub PAT with `repo` scope |
| `runner_version` | string | `""` (latest) | Specific runner version to download |
| `runners_base` | string | `./runners` | Base directory for runner instances |
| `default_labels` | list | `[]` | Labels applied to all runners |
| `runner_group` | string | `""` | Runner group (Enterprise/org only) |
| `health_check_interval` | int | `30` | Seconds between health checks |
| `log_level` | string | `INFO` | Logging level |
| `log_file` | string | `./orchestrator.log` | Log file path |
| `repositories` | list | — | List of repos (see below) |

### Repository entry

| Key | Type | Default | Description |
|---|---|---|---|
| `owner` | string | — | GitHub user/org |
| `repo` | string | — | Repository name |
| `labels` | list | `[]` | Extra labels for this runner |
| `pat` | string | `null` | Per-repo PAT override |

### Environment variables

| Variable | Overrides |
|---|---|
| `GITHUB_PAT` | `github_pat` in config |
| `RUNNERS_BASE` | `runners_base` in config |
| `LOG_LEVEL` | `log_level` in config |

## How runner registration works

1. The orchestrator calls the GitHub API to get a short-lived **registration token** for each repository
2. It runs the official `config.sh` with `--unattended` to register the runner
3. It starts `run.sh` as a background process
4. A health monitor thread checks every N seconds and auto-restarts crashed runners
5. On `SIGINT` / `SIGTERM`, runners are gracefully stopped via `SIGINT` → `SIGKILL` fallback

## Cleaning up

```bash
# Stop runners and deregister from GitHub:
make unregister

# Nuclear option — deregister + delete all runner files:
make destroy

# Remove downloaded runner binary + logs:
make clean
```

## Requirements

- Python 3.10+
- macOS (arm64/x64) or Linux (x64/arm64)
- GitHub PAT with `repo` scope
- Network access to github.com

## License

MIT
