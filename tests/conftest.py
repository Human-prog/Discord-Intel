"""Shared pytest fixtures.

Tests are isolated from the machine environment:
- every settings-related environment variable is removed before each test,
- tests construct Settings with _env_file=None so no developer .env file
  ever influences the run.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from project_intelligence.config import Settings, env_var_names


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture()
def make_settings():
    """Factory that builds Settings with .env loading disabled."""

    def _make(**kwargs) -> Settings:
        kwargs.setdefault("_env_file", None)
        return Settings(**kwargs)

    return _make
