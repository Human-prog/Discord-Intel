"""Integrations module for external services (Phase 12+).

Provides GitHub, Ollama, research, and OpenCode integration abstractions.
All integrations are read-only by default and require explicit configuration.
"""

from __future__ import annotations

from .github import GitHubIntegration, create_github_integration
from .ollama import ModelAdapter, OllamaClient, create_model_adapter, create_ollama_client
from .opencode import (
    MockOpenCodeAdapter,
    OpenCodeAdapter,
    create_mock_adapter,
    create_opencode_adapter,
)

__all__ = [
    "GitHubIntegration",
    "MockOpenCodeAdapter",
    "ModelAdapter",
    "OllamaClient",
    "OpenCodeAdapter",
    "create_github_integration",
    "create_mock_adapter",
    "create_model_adapter",
    "create_ollama_client",
    "create_opencode_adapter",
]
