"""
GitHub API helpers — registration token management.
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"GitHub API {status}: {message}")


def _headers(pat: str) -> dict[str, str]:
    return {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_registration_token(owner: str, repo: str, pat: str) -> str:
    """
    Request a short-lived registration token for a self-hosted runner.
    https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runners/registration-token"
    resp = requests.post(url, headers=_headers(pat), timeout=30)

    if resp.status_code != 201:
        raise GitHubAPIError(resp.status_code, resp.text)

    data = resp.json()
    token: str = data["token"]
    expires = data.get("expires_at", "unknown")
    logger.info("Registration token for %s/%s expires at %s", owner, repo, expires)
    return token


def get_removal_token(owner: str, repo: str, pat: str) -> str:
    """
    Request a short-lived removal token for deregistering a runner.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runners/remove-token"
    resp = requests.post(url, headers=_headers(pat), timeout=30)

    if resp.status_code != 201:
        raise GitHubAPIError(resp.status_code, resp.text)

    removal_token: str = resp.json()["token"]
    return removal_token


def list_runners(owner: str, repo: str, pat: str) -> list[dict[str, object]]:
    """List all self-hosted runners registered for a repository."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runners"
    resp = requests.get(url, headers=_headers(pat), timeout=30)

    if resp.status_code != 200:
        raise GitHubAPIError(resp.status_code, resp.text)

    runners: list[dict[str, object]] = resp.json().get("runners", [])
    return runners


def verify_pat(pat: str) -> dict[str, object]:
    """Verify the PAT is valid and return the authenticated user info."""
    resp = requests.get(f"{GITHUB_API}/user", headers=_headers(pat), timeout=15)
    if resp.status_code != 200:
        raise GitHubAPIError(resp.status_code, "PAT verification failed")
    result: dict[str, object] = resp.json()
    return result
