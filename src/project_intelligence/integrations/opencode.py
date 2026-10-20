"""OpenCode Read-Only Integration (Phase 17).

Isolated, optional OpenCode integration.  Disabled by default.
Provides an adapter interface and mock for tests.  Read-only session/project
metadata only.  No unrestricted shell, terminal, filesystem, edit, or
tool-execution access.
"""

from __future__ import annotations

from typing import Any, Optional

from project_intelligence.config import Settings, load_settings


# ---------------------------------------------------------------------------
# OpenCode adapter interface
# ---------------------------------------------------------------------------

class OpenCodeAdapter:
    """Adapter interface for OpenCode integration (read-only)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.opencode_enabled

    def is_enabled(self) -> bool:
        """Check if OpenCode integration is enabled."""
        return self.enabled

    def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        """Get read-only session metadata (disabled by default)."""
        if not self.is_enabled():
            return None
        # Placeholder: actual OpenCode API call would go here
        return None

    def get_project_metadata(self, project_id: str) -> dict[str, Any] | None:
        """Get read-only project metadata (disabled by default)."""
        if not self.is_enabled():
            return None
        # Placeholder: actual OpenCode API call would go here
        return None

    def list_sessions(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        """List read-only sessions (disabled by default)."""
        if not self.is_enabled():
            return []
        return []


class MockOpenCodeAdapter(OpenCodeAdapter):
    """Mock adapter for testing (no network requests)."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(settings or load_settings())
        self._sessions: list[dict[str, Any]] = []
        self._projects: list[dict[str, Any]] = []

    def add_session(self, session: dict[str, Any]) -> None:
        """Add a mock session for testing."""
        self._sessions.append(session)

    def add_project(self, project: dict[str, Any]) -> None:
        """Add a mock project for testing."""
        self._projects.append(project)

    def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None
        for session in self._sessions:
            if session.get("id") == session_id:
                return session
        return None

    def get_project_metadata(self, project_id: str) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None
        for project in self._projects:
            if project.get("id") == project_id:
                return project
        return None

    def list_sessions(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        if not self.is_enabled():
            return []
        if project_id:
            return [s for s in self._sessions if s.get("project_id") == project_id]
        return self._sessions


def create_opencode_adapter(settings: Optional[Settings] = None) -> OpenCodeAdapter:
    """Factory for OpenCodeAdapter."""
    if settings is None:
        settings = load_settings()
    return OpenCodeAdapter(settings)


def create_mock_adapter(settings: Optional[Settings] = None) -> MockOpenCodeAdapter:
    """Factory for MockOpenCodeAdapter (testing only)."""
    if settings is None:
        settings = load_settings()
    return MockOpenCodeAdapter(settings)