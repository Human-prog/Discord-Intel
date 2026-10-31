"""Integration adapter tests: GitHub, Ollama, OpenCode (Phases 12, 17)."""

from __future__ import annotations

from project_intelligence.integrations import ollama as ollama_module
from project_intelligence.integrations.github import (
    GitHubIntegration,
    create_github_integration,
)
from project_intelligence.integrations.ollama import ModelAdapter, OllamaClient
from project_intelligence.integrations.opencode import (
    MockOpenCodeAdapter,
    OpenCodeAdapter,
    create_mock_adapter,
    create_opencode_adapter,
)

# ---------------------------------------------------------------------------
# GitHub (read-only)
# ---------------------------------------------------------------------------


def test_github_is_disabled_by_default(make_settings) -> None:
    github = GitHubIntegration(make_settings())
    assert github.is_enabled() is False
    assert github.get_repo_metadata("owner/repo") is None
    assert github.get_recent_commits("owner/repo") == []
    assert github.get_issues("owner/repo") == []
    assert github.get_pull_requests("owner/repo") == []
    assert github.get_releases("owner/repo") == []
    assert github.get_ci_status("owner/repo") is None


def test_github_token_mode_scopes_repositories(make_settings) -> None:
    github = GitHubIntegration(
        make_settings(
            github_mode="token",
            github_read_only_token="ghp_notarealtokenvalue",
            github_allowed_repositories=["owner/repo"],
        )
    )
    assert github.is_enabled() is True
    assert github.is_repo_allowed("owner/repo") is True
    assert github.is_repo_allowed("owner/other") is False

    metadata = github.get_repo_metadata("owner/repo")
    assert metadata == {"name": "owner/repo", "status": "not_fetched", "cached": False}
    assert github.get_repo_metadata("owner/other") is None
    assert github.get_recent_commits("owner/repo") == []


def test_github_factory(make_settings) -> None:
    github = create_github_integration(make_settings())
    assert isinstance(github, GitHubIntegration)


# ---------------------------------------------------------------------------
# Ollama (fake HTTP transport)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, *, status_code: int = 200, payload: dict | None = None, raises: bool = False):
        self._status = status_code
        self._payload = payload or {}
        self._raises = raises
        self.posted: list[dict] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def get(self, url: str) -> _FakeResponse:
        if self._raises:
            raise RuntimeError("connection refused")
        return _FakeResponse(self._status, self._payload)

    def post(self, url: str, json: dict | None = None) -> _FakeResponse:
        self.posted.append({"url": url, "json": json or {}})
        return _FakeResponse(self._status, self._payload)


def _patch_client(monkeypatch, client: _FakeClient) -> None:
    monkeypatch.setattr(ollama_module.httpx, "Client", lambda *args, **kwargs: client)


def test_ollama_unavailable_returns_fallbacks(make_settings, monkeypatch) -> None:
    client = _FakeClient(raises=True)
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3"))
    assert ollama.is_available() is False
    assert ollama.list_models() == []
    assert ollama.generate("hello") is None
    assert client.posted == []


def test_ollama_lists_models(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"models": [{"name": "llama3"}, {"name": "qwen"}]})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3"))
    assert ollama.list_models() == ["llama3", "qwen"]


def test_ollama_generate_requires_configured_model(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": "hi"})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model=None))
    assert ollama.generate("hello") is None


def test_ollama_generate_returns_response(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": "hello back"})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3", ollama_timeout_seconds=5))
    assert ollama.generate("hello", max_tokens=10) == "hello back"
    assert client.posted
    assert client.posted[0]["json"]["model"] == "llama3"
    assert client.posted[0]["json"]["options"]["num_predict"] == 10


def test_ollama_generate_truncates_long_prompts(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": "ok"})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3"))
    ollama.generate("x" * 9_000)
    sent = client.posted[0]["json"]["prompt"]
    assert sent.endswith("[truncated]")
    assert len(sent) <= 9_000


def test_ollama_generate_structured_parses_json(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": 'Here: {"answer": 42}'})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3"))
    assert ollama.generate_structured("question", {"type": "object"}) == {"answer": 42}


def test_ollama_generate_structured_rejects_non_json(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": "no json here"})
    _patch_client(monkeypatch, client)

    ollama = OllamaClient(make_settings(ollama_model="llama3"))
    assert ollama.generate_structured("question", {"type": "object"}) is None


def test_model_adapter_summarizes(make_settings, monkeypatch) -> None:
    client = _FakeClient(payload={"response": "summary"})
    _patch_client(monkeypatch, client)

    adapter = ModelAdapter(OllamaClient(make_settings(ollama_model="llama3")))
    assert adapter.summarize("evidence") == "summary"


# ---------------------------------------------------------------------------
# OpenCode (read-only, disabled by default)
# ---------------------------------------------------------------------------


def test_opencode_is_disabled_by_default(make_settings) -> None:
    adapter = create_opencode_adapter(make_settings())
    assert isinstance(adapter, OpenCodeAdapter)
    assert adapter.is_enabled() is False
    assert adapter.get_session_metadata("s1") is None
    assert adapter.get_project_metadata("p1") is None
    assert adapter.list_sessions() == []


def test_opencode_enabled_placeholder_is_read_only(make_settings, tmp_path) -> None:
    adapter = create_opencode_adapter(
        make_settings(
            opencode_enabled=True,
            opencode_command="opencode",
            opencode_allowed_worktrees=[tmp_path],
        )
    )
    assert adapter.is_enabled() is True
    assert adapter.get_session_metadata("s1") is None
    assert adapter.list_sessions() == []


def test_mock_adapter_returns_registered_metadata(make_settings, tmp_path) -> None:
    adapter = create_mock_adapter(
        make_settings(
            opencode_enabled=True,
            opencode_command="opencode",
            opencode_allowed_worktrees=[tmp_path],
        )
    )
    assert isinstance(adapter, MockOpenCodeAdapter)

    adapter.add_session({"id": "s1", "project_id": "p1", "title": "Session"})
    adapter.add_project({"id": "p1", "name": "Project"})

    assert adapter.get_session_metadata("s1") == {
        "id": "s1",
        "project_id": "p1",
        "title": "Session",
    }
    assert adapter.get_session_metadata("missing") is None
    assert adapter.get_project_metadata("p1") == {"id": "p1", "name": "Project"}
    assert adapter.list_sessions() == [{"id": "s1", "project_id": "p1", "title": "Session"}]
    assert adapter.list_sessions(project_id="p1") == [{"id": "s1", "project_id": "p1", "title": "Session"}]
    assert adapter.list_sessions(project_id="other") == []


def test_mock_adapter_disabled_when_integration_disabled(make_settings) -> None:
    adapter = create_mock_adapter(make_settings(opencode_enabled=False))
    adapter.add_session({"id": "s1"})
    assert adapter.get_session_metadata("s1") is None
    assert adapter.list_sessions() == []


def test_opencode_factories_accept_no_settings(monkeypatch) -> None:
    from project_intelligence.config import Settings
    from project_intelligence.integrations import opencode as opencode_module

    monkeypatch.setattr(opencode_module, "load_settings", lambda: Settings(_env_file=None))
    for factory in (create_opencode_adapter, create_mock_adapter):
        adapter = factory()
        assert adapter is not None
