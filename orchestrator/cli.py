"""
CLI entry point for the actions-orchestrator.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import load_config
from .orchestrator import Orchestrator


def setup_logging(level: str, log_file: str | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format=fmt, datefmt=datefmt, handlers=handlers)


def cmd_start(args: argparse.Namespace) -> None:
    """Start all runners and monitor them."""
    config = load_config(args.config)
    setup_logging(config.log_level, config.log_file)
    orch = Orchestrator(config)
    orch.run()


def cmd_setup(args: argparse.Namespace) -> None:
    """Download runner + provision + configure (without starting)."""
    config = load_config(args.config)
    setup_logging(config.log_level, config.log_file)
    orch = Orchestrator(config)
    orch.setup()
    print(f"\n✓ {len(orch.runners)} runner(s) configured and ready to start")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop all running runners."""
    config = load_config(args.config)
    setup_logging(config.log_level, config.log_file)
    orch = Orchestrator(config)
    # Re-hydrate runner instances from existing directories
    from .runner import RunnerInstance
    from .orchestrator import TEMPLATE_DIR
    for repo_cfg in config.repositories:
        runner = RunnerInstance(config, repo_cfg, TEMPLATE_DIR)
        orch.runners.append(runner)
    orch.stop_all()
    print("✓ All runners stopped")


def cmd_unregister(args: argparse.Namespace) -> None:
    """Unregister all runners from GitHub."""
    config = load_config(args.config)
    setup_logging(config.log_level, config.log_file)
    orch = Orchestrator(config)
    from .runner import RunnerInstance
    from .orchestrator import TEMPLATE_DIR
    for repo_cfg in config.repositories:
        runner = RunnerInstance(config, repo_cfg, TEMPLATE_DIR)
        orch.runners.append(runner)
    orch.unregister_all()
    print("✓ All runners unregistered")


def cmd_destroy(args: argparse.Namespace) -> None:
    """Unregister + remove all runner directories."""
    config = load_config(args.config)
    setup_logging(config.log_level, config.log_file)
    orch = Orchestrator(config)
    from .runner import RunnerInstance
    from .orchestrator import TEMPLATE_DIR
    for repo_cfg in config.repositories:
        runner = RunnerInstance(config, repo_cfg, TEMPLATE_DIR)
        orch.runners.append(runner)
    orch.destroy_all()
    print("✓ All runners destroyed")


def cmd_status(args: argparse.Namespace) -> None:
    """Show status of runners."""
    config = load_config(args.config)
    setup_logging(config.log_level)

    from .github_api import list_runners

    print(f"{'Repository':<40} {'GitHub Runners'}")
    print("-" * 70)
    for repo_cfg in config.repositories:
        pat = config.pat_for(repo_cfg)
        try:
            runners = list_runners(repo_cfg.owner, repo_cfg.repo, pat)
            for r in runners:
                status = r.get("status", "unknown")
                name = r.get("name", "?")
                labels = ", ".join(l["name"] for l in r.get("labels", []))
                print(f"  {repo_cfg.full_name:<38} {name:<20} {status:<10} [{labels}]")
            if not runners:
                print(f"  {repo_cfg.full_name:<38} (no runners registered)")
        except Exception as exc:
            print(f"  {repo_cfg.full_name:<38} ERROR: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="actions-orchestrator",
        description="Manage multiple GitHub Actions self-hosted runners on one machine.",
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="Start all runners and monitor them")
    sub.add_parser("setup", help="Download, provision, and configure runners (no start)")
    sub.add_parser("stop", help="Stop all running runners")
    sub.add_parser("status", help="Show runner status from GitHub API")
    sub.add_parser("unregister", help="Unregister all runners from GitHub")
    sub.add_parser("destroy", help="Unregister and delete all runner directories")

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "setup": cmd_setup,
        "stop": cmd_stop,
        "status": cmd_status,
        "unregister": cmd_unregister,
        "destroy": cmd_destroy,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
