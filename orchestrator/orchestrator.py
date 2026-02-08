"""
Orchestrator — manages the fleet of runner instances.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .config import Config, load_config
from .github_api import verify_pat
from .runner import RunnerInstance, RunnerState

logger = logging.getLogger(__name__)

# Resolve relative to the project root (parent of orchestrator/ package)
TEMPLATE_DIR = (Path(__file__).resolve().parent.parent / "_runner_template")


class Orchestrator:
    """
    Top-level controller that:
      1. Downloads the runner binary (once)
      2. Provisions per-repo directories
      3. Configures & starts each runner
      4. Monitors health and auto-restarts crashed runners
      5. Handles graceful shutdown on SIGINT / SIGTERM
    """

    def __init__(self, config: Config):
        self.config = config
        self.runners: list[RunnerInstance] = []
        self._shutdown_event = threading.Event()
        self._health_thread: Optional[threading.Thread] = None

    # ── Bootstrap ───────────────────────────────────────────────────

    def _download_runner(self) -> None:
        """Download the runner binary into the template directory."""
        script = Path(__file__).resolve().parent.parent / "scripts" / "download-runner.sh"
        if not script.exists():
            raise FileNotFoundError(f"Download script not found: {script}")

        cmd = [str(script), self.config.runner_version, str(TEMPLATE_DIR)]
        logger.info("Downloading runner binary…")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise RuntimeError(f"Runner download failed:\n{result.stderr}")

        logger.info(result.stdout.strip())

    def _verify_credentials(self) -> None:
        """Verify the GitHub PAT is valid."""
        user = verify_pat(self.config.github_pat)
        logger.info("Authenticated as GitHub user: %s", user.get("login", "unknown"))

    # ── Lifecycle ───────────────────────────────────────────────────

    def setup(self) -> None:
        """Full setup: download runner, provision all repos, configure them (force replace)."""
        self._verify_credentials()
        self._download_runner()
        self._provision_and_configure(replace=True)
        logger.info("Setup complete — %d runner(s) configured", len(self.runners))

    def prepare(self) -> None:
        """Ensure runners are provisioned and configured, but skip if already set up."""
        self._verify_credentials()
        self._download_runner()
        self._provision_and_configure(replace=False)

    def _provision_and_configure(self, *, replace: bool) -> None:
        self.config.runners_base.mkdir(parents=True, exist_ok=True)
        self.runners.clear()

        for repo_cfg in self.config.repositories:
            runner = RunnerInstance(self.config, repo_cfg, TEMPLATE_DIR)
            runner.provision()
            runner.configure(replace=replace)
            self.runners.append(runner)

    def start_all(self) -> None:
        """Start all configured runners."""
        for runner in self.runners:
            try:
                if runner.state == RunnerState.UNINITIALIZED:
                    runner.provision()
                    runner.configure(replace=False)
                runner.start()
            except Exception:
                logger.exception("Failed to start runner for %s", runner.repo.full_name)

        logger.info("All runners started (%d)", len(self.runners))

    def stop_all(self) -> None:
        """Stop all running runners."""
        logger.info("Stopping all runners…")
        for runner in self.runners:
            try:
                runner.stop()
            except Exception:
                logger.exception("Error stopping runner for %s", runner.repo.full_name)

    def unregister_all(self) -> None:
        """Unregister all runners from GitHub."""
        logger.info("Unregistering all runners…")
        for runner in self.runners:
            try:
                runner.unregister()
            except Exception:
                logger.exception("Error unregistering runner for %s", runner.repo.full_name)

    def destroy_all(self) -> None:
        """Unregister and remove all runner directories."""
        logger.info("Destroying all runners…")
        for runner in self.runners:
            try:
                runner.destroy()
            except Exception:
                logger.exception("Error destroying runner for %s", runner.repo.full_name)
        self.runners.clear()

    # ── Health monitoring ───────────────────────────────────────────

    def _health_loop(self) -> None:
        """Background thread: periodically check runners and restart crashed ones."""
        while not self._shutdown_event.is_set():
            for runner in self.runners:
                if self._shutdown_event.is_set():
                    return
                if not runner.health_check():
                    logger.warning("[%s] Runner down — restarting", runner.repo.full_name)
                    try:
                        runner.restart()
                    except Exception:
                        logger.exception("Failed to restart %s", runner.repo.full_name)

            self._shutdown_event.wait(self.config.health_check_interval)

    def _start_health_monitor(self) -> None:
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True, name="health-monitor"
        )
        self._health_thread.start()

    # ── Signal handling ─────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        def handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info("Received %s — shutting down gracefully", sig_name)
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    # ── Main entry point ────────────────────────────────────────────

    def run(self) -> None:
        """
        Full lifecycle: setup → start → monitor → shutdown.
        Blocks until SIGINT/SIGTERM is received.
        """
        self._install_signal_handlers()

        logger.info("=" * 60)
        logger.info("Actions Orchestrator starting")
        logger.info(
            "Managing %d repository runner(s)", len(self.config.repositories)
        )
        logger.info("=" * 60)

        self.prepare()
        self.start_all()
        self._start_health_monitor()

        logger.info("Orchestrator running. Press Ctrl+C to stop.")

        # Block until shutdown signal
        self._shutdown_event.wait()

        self.stop_all()
        logger.info("All runners stopped. Goodbye.")

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> list[dict]:
        """Return a summary of all runners."""
        results = []
        for r in self.runners:
            results.append({
                "repo": r.repo.full_name,
                "state": r.state.name,
                "pid": r.pid,
                "runner_dir": str(r.runner_dir),
            })
        return results
