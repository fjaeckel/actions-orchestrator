"""
Configuration loader — reads config.yaml + .env overrides.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass
class RepoConfig:
    owner: str
    repo: str
    labels: list[str] = field(default_factory=list)
    pat: str | None = None  # per-repo override

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def dir_name(self) -> str:
        return f"{self.owner}-{self.repo}"


@dataclass
class Config:
    github_pat: str
    runners_base: Path
    repositories: list[RepoConfig]
    runner_version: str = ""
    default_labels: list[str] = field(default_factory=list)
    runner_group: str = ""
    health_check_interval: int = 30
    log_level: str = "INFO"
    log_file: str = "./orchestrator.log"

    def pat_for(self, repo: RepoConfig) -> str:
        """Return the PAT to use for a given repo (per-repo override or global)."""
        return repo.pat or self.github_pat


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\nCopy config.yaml.example to config.yaml and fill in your values."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    # Environment overrides
    pat = os.environ.get("GITHUB_PAT") or raw.get("github_pat", "")
    runners_base = os.environ.get("RUNNERS_BASE") or raw.get("runners_base", "./runners")
    log_level = os.environ.get("LOG_LEVEL") or raw.get("log_level", "INFO")

    repos = [
        RepoConfig(
            owner=r["owner"],
            repo=r["repo"],
            labels=r.get("labels", []),
            pat=r.get("pat"),
        )
        for r in raw.get("repositories", [])
    ]

    if not pat:
        raise ValueError("No GitHub PAT configured. Set GITHUB_PAT env var or github_pat in config.yaml")

    if not repos:
        raise ValueError("No repositories configured in config.yaml")

    return Config(
        github_pat=pat,
        runners_base=Path(runners_base),
        repositories=repos,
        runner_version=raw.get("runner_version", ""),
        default_labels=raw.get("default_labels", []),
        runner_group=raw.get("runner_group", ""),
        health_check_interval=raw.get("health_check_interval", 30),
        log_level=log_level,
        log_file=raw.get("log_file", "./orchestrator.log"),
    )
