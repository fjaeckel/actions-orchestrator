"""
RunnerInstance — manages a single GitHub Actions runner process for one repository.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import signal
import subprocess
import time
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from .config import Config, RepoConfig
from .github_api import get_registration_token, get_removal_token

logger = logging.getLogger(__name__)


class RunnerState(Enum):
    UNINITIALIZED = auto()
    CONFIGURED = auto()
    RUNNING = auto()
    STOPPED = auto()
    ERROR = auto()


class RunnerInstance:
    """Manages the lifecycle of a single Actions runner bound to one repo."""

    def __init__(self, config: Config, repo: RepoConfig, template_dir: Path):
        self.config = config
        self.repo = repo
        self.template_dir = template_dir.resolve()
        self.runner_dir = (config.runners_base / repo.dir_name).resolve()
        self.state = RunnerState.UNINITIALIZED
        self._process: Optional[subprocess.Popen] = None
        self._runner_name = f"{platform.node()}-{repo.dir_name}"

    # ── Properties ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    @property
    def exit_code(self) -> Optional[int]:
        if self._process is None:
            return None
        return self._process.poll()

    # ── Setup ───────────────────────────────────────────────────────

    def provision(self) -> None:
        """Copy runner binaries into the runner's own directory."""
        if self.runner_dir.exists() and (self.runner_dir / "config.sh").exists():
            logger.info("[%s] Runner directory already exists, skipping copy", self.repo.full_name)
            return

        logger.info("[%s] Provisioning runner directory: %s", self.repo.full_name, self.runner_dir)
        self.runner_dir.mkdir(parents=True, exist_ok=True)

        # Copy template contents (not the dir itself) into the runner dir
        for item in self.template_dir.iterdir():
            dest = self.runner_dir / item.name
            if dest.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

    def configure(self, *, replace: bool = False) -> None:
        """
        Run `config.sh` to register this runner with the repository.
        Obtains a registration token via the GitHub API.
        """
        if not (self.runner_dir / "config.sh").exists():
            raise FileNotFoundError(
                f"Runner not provisioned at {self.runner_dir}. Call provision() first."
            )

        # If already configured and not replacing, skip
        credentials = self.runner_dir / ".credentials"
        if credentials.exists() and not replace:
            logger.info("[%s] Runner already configured, skipping", self.repo.full_name)
            self.state = RunnerState.CONFIGURED
            return

        pat = self.config.pat_for(self.repo)
        reg_token = get_registration_token(self.repo.owner, self.repo.repo, pat)

        labels = list(self.config.default_labels) + list(self.repo.labels)
        label_str = ",".join(labels) if labels else ""

        url = f"https://github.com/{self.repo.owner}/{self.repo.repo}"

        cmd = [
            "./config.sh",
            "--url", url,
            "--token", reg_token,
            "--name", self._runner_name,
            "--work", "_work",
            "--unattended",
        ]

        if replace:
            cmd.append("--replace")

        if label_str:
            cmd.extend(["--labels", label_str])

        if self.config.runner_group:
            cmd.extend(["--runnergroup", self.config.runner_group])

        logger.info("[%s] Configuring runner '%s' → %s", self.repo.full_name, self._runner_name, url)

        result = subprocess.run(
            cmd,
            cwd=self.runner_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("[%s] config.sh failed:\nstdout: %s\nstderr: %s",
                         self.repo.full_name, result.stdout, result.stderr)
            self.state = RunnerState.ERROR
            raise RuntimeError(f"Runner configuration failed for {self.repo.full_name}")

        logger.info("[%s] Runner configured successfully", self.repo.full_name)
        self.state = RunnerState.CONFIGURED

    # ── Run ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the runner process (non-blocking)."""
        if self.is_running:
            logger.warning("[%s] Runner already running (pid %s)", self.repo.full_name, self.pid)
            return

        run_sh = self.runner_dir / "run.sh"
        if not run_sh.exists():
            raise FileNotFoundError(f"run.sh not found in {self.runner_dir}")

        log_path = self.runner_dir / "runner.log"
        log_file = open(log_path, "a")

        logger.info("[%s] Starting runner (log → %s)", self.repo.full_name, log_path)

        self._process = subprocess.Popen(
            ["./run.sh"],
            cwd=self.runner_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # detach from our process group
        )

        self.state = RunnerState.RUNNING
        logger.info("[%s] Runner started (pid %s)", self.repo.full_name, self.pid)

    def stop(self, timeout: int = 30) -> None:
        """Gracefully stop the runner process."""
        if not self.is_running:
            logger.info("[%s] Runner not running, nothing to stop", self.repo.full_name)
            self.state = RunnerState.STOPPED
            return

        logger.info("[%s] Sending SIGINT to runner (pid %s)", self.repo.full_name, self.pid)
        try:
            os.killpg(os.getpgid(self._process.pid), signal.SIGINT)
        except ProcessLookupError:
            self.state = RunnerState.STOPPED
            return

        try:
            self._process.wait(timeout=timeout)
            logger.info("[%s] Runner stopped gracefully", self.repo.full_name)
        except subprocess.TimeoutExpired:
            logger.warning("[%s] Runner did not stop in %ds, sending SIGKILL", self.repo.full_name, timeout)
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._process.wait(timeout=10)

        self.state = RunnerState.STOPPED

    def restart(self) -> None:
        """Stop and re-start the runner."""
        logger.info("[%s] Restarting runner", self.repo.full_name)
        self.stop()
        time.sleep(2)
        self.start()

    # ── Cleanup ─────────────────────────────────────────────────────

    def unregister(self) -> None:
        """Deregister the runner from GitHub."""
        self.stop()

        pat = self.config.pat_for(self.repo)
        try:
            removal_token = get_removal_token(self.repo.owner, self.repo.repo, pat)
        except Exception as exc:
            logger.error("[%s] Failed to get removal token: %s", self.repo.full_name, exc)
            return

        cmd = [
            "./config.sh",
            "remove",
            "--token", removal_token,
        ]

        logger.info("[%s] Unregistering runner", self.repo.full_name)
        result = subprocess.run(cmd, cwd=self.runner_dir, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.error("[%s] Unregister failed: %s", self.repo.full_name, result.stderr)
        else:
            logger.info("[%s] Runner unregistered", self.repo.full_name)

    def destroy(self) -> None:
        """Unregister and remove the runner directory entirely."""
        self.unregister()
        if self.runner_dir.exists():
            logger.info("[%s] Removing runner directory: %s", self.repo.full_name, self.runner_dir)
            shutil.rmtree(self.runner_dir)

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Return True if the runner process is alive."""
        if not self.is_running:
            exit_code = self.exit_code
            logger.warning("[%s] Runner is not running (exit code: %s)", self.repo.full_name, exit_code)
            self.state = RunnerState.ERROR
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"RunnerInstance(repo={self.repo.full_name!r}, "
            f"state={self.state.name}, pid={self.pid})"
        )
