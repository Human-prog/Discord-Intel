"""GitHub Read-Only Integration (Phase 12).

Provides a GitHub integration abstraction supporting both GitHub App
(preferred) and fine-grained read-only token (fallback).  Access is
restricted to explicitly mapped repositories only.

All operations are read-only: no create, edit, merge, delete, or push.
"""

from __future__ import annotations

import time
from typing import Any

from project_intelligence.config import Settings, load_settings

# ---------------------------------------------------------------------------
# GitHub integration abstraction
# ---------------------------------------------------------------------------


class GitHubIntegration:
    """GitHub read-only integration abstraction.

    Supports two authentication modes:
    - "app": GitHub App with installation token
    - "token": Fine-grained read-only personal access token

    All operations are read-only and restricted to mapped repositories.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.github_mode
        self.allowed_repos = settings.github_allowed_repositories
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes

    def is_enabled(self) -> bool:
        """Check if GitHub integration is configured."""
        return self.mode in ("app", "token")

    def is_repo_allowed(self, repo: str) -> bool:
        """Check if a repository is in the allowed list."""
        return repo in self.allowed_repos

    def get_repo_metadata(self, repo: str) -> dict[str, Any] | None:
        """Fetch repository metadata (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return None
        # Cache check
        cache_key = f"metadata:{repo}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return data
        # Placeholder: actual API call would go here
        return {"name": repo, "status": "not_fetched", "cached": False}

    def get_recent_commits(self, repo: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent commits (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return []
        return []

    def get_issues(self, repo: str, state: str = "open") -> list[dict[str, Any]]:
        """Fetch issues (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return []
        return []

    def get_pull_requests(self, repo: str, state: str = "open") -> list[dict[str, Any]]:
        """Fetch pull requests (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return []
        return []

    def get_releases(self, repo: str) -> list[dict[str, Any]]:
        """Fetch releases (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return []
        return []

    def get_ci_status(self, repo: str) -> dict[str, Any] | None:
        """Fetch CI/workflow status (read-only)."""
        if not self.is_enabled() or not self.is_repo_allowed(repo):
            return None
        return None


def create_github_integration(settings: Settings | None = None) -> GitHubIntegration:
    """Factory for GitHubIntegration."""
    if settings is None:
        settings = load_settings()
    return GitHubIntegration(settings)
