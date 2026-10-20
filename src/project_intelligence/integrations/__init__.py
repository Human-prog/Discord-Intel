"""Integrations module for external services (Phase 12+).

Provides GitHub, Ollama, research, and OpenCode integration abstractions.
All integrations are read-only by default and require explicit configuration.
"""

from __future__ import annotations

from .github import GitHubIntegration, create_github_integration  # noqa: F401
from .ollama import OllamaClient, ModelAdapter, create_ollama_client, create_model_adapter  # noqa: F401
from .opencode import OpenCodeAdapter, MockOpenCodeAdapter, create_opencode_adapter, create_mock_adapter  # noqa: F401

__all__ = [
    "GitHubIntegration",
    "create_github_integration",
    "OllamaClient",
    "ModelAdapter",
    "create_ollama_client",
    "create_model_adapter",
    "OpenCodeAdapter",
    "MockOpenCodeAdapter",
    "create_opencode_adapter",
    "create_mock_adapter",
]