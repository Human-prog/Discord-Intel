"""Dashboard API and mobile UI tests (Phase 7/8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from project_intelligence.dashboard import dashboard
from project_intelligence.health.health_engine import store_health_snapshot
from project_intelligence.storage import repositories as repo


@pytest.fixture(autouse=True)
def _clear_login_attempts():
    dashboard._LOGIN_ATTEMPTS.clear()
    yield
    dashboard._LOGIN_ATTEMPTS.clear()


@pytest.fixture()
def client(app_settings):
    from project_intelligence.dashboard.dashboard import app

    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, app_settings) -> None:
    secret = Path(app_settings.dashboard_session_secret_file).read_text(encoding="utf-8").strip()
    response = client.post("/auth/session", json={"token": secret})
    assert response.status_code == 200, response.text


def _project(db, name: str = "Alpha", root: str = "/srv/alpha"):
    return repo.upsert_project(db, name, f"{name} description", root)


# ---------------------------------------------------------------------------
# Public endpoints and UI
# ---------------------------------------------------------------------------


def test_health_is_public(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database_healthy"] is True
    assert body["app_env"] == "testing"
    assert body["dashboard_bound_host"] == "127.0.0.1"
    assert isinstance(body["uptime_seconds"], (int, float))


def test_mobile_ui_is_served(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Project Intelligence" in response.text
    assert "viewport-fit=cover" in response.text


def test_favicon_is_empty(client) -> None:
    assert client.get("/favicon.ico").status_code == 204


def test_session_status_is_public(client) -> None:
    response = client.get("/auth/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "expires_at_utc": None}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_data_endpoints_require_authentication(client) -> None:
    for path in ("/projects", "/projects/1", "/activity/recent"):
        assert client.get(path).status_code == 401, path


def test_wrong_secret_is_rejected(client) -> None:
    response = client.post("/auth/session", json={"token": "not-the-secret"})
    assert response.status_code == 401
    assert "dpi_owner_session" not in client.cookies


def test_sign_in_sets_http_only_cookie(client, app_settings) -> None:
    secret = Path(app_settings.dashboard_session_secret_file).read_text(encoding="utf-8").strip()
    response = client.post("/auth/session", json={"token": secret})
    assert response.status_code == 200
    assert response.json()["authenticated"] is True

    cookie = response.headers["set-cookie"]
    assert "dpi_owner_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie or "samesite=strict" in cookie

    assert client.get("/auth/session").json()["authenticated"] is True
    assert client.get("/projects").status_code == 200


def test_owner_session_ignores_discord_allowlists(client, app_settings, monkeypatch) -> None:
    """The browser owner session has no guild/channel and must not be scoped to them."""
    monkeypatch.setenv("DISCORD_ALLOWED_GUILD_IDS", "222222222222222222")
    monkeypatch.setenv("DISCORD_ALLOWED_CHANNEL_IDS", "333333333333333333")
    _login(client, app_settings)
    assert client.get("/projects").status_code == 200
    assert client.get("/activity/recent").status_code == 200


def test_source_path_does_not_touch_secure_cookie_over_http(client, app_settings) -> None:
    """Testing/dev runs on loopback HTTP, so the cookie must not be Secure."""
    _login(client, app_settings)
    assert client.get("/auth/session").json()["authenticated"] is True


def test_sign_out_clears_the_session(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/projects").status_code == 200

    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "expires_at_utc": None}
    assert client.get("/projects").status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client) -> None:
    for _ in range(dashboard._LOGIN_MAX_ATTEMPTS):
        assert client.post("/auth/session", json={"token": "wrong"}).status_code == 401

    response = client.post("/auth/session", json={"token": "wrong"})
    assert response.status_code == 429


def test_cookie_authentication_is_not_accepted_for_writes(client, app_settings) -> None:
    _login(client, app_settings)
    response = client.post("/projects/1/milestones", json={"title": "Ship"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_project_list_is_empty_at_first(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/projects").json() == []


def test_project_list_reports_health(client, db, app_settings) -> None:
    project = _project(db)
    store_health_snapshot(project.id, "healthy", details={"root_exists": True})
    _login(client, app_settings)

    response = client.get("/projects")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == project.id
    assert body[0]["name"] == "Alpha"
    assert body[0]["status"] == "healthy"
    assert body[0]["last_checked"].endswith("Z")


def test_project_without_snapshot_reports_unknown(client, db, app_settings) -> None:
    _project(db)
    _login(client, app_settings)
    assert client.get("/projects").json()[0]["status"] == "unknown"


def test_project_list_filters_by_name_and_status(client, db, app_settings) -> None:
    alpha = _project(db, "Alpha", "/srv/alpha")
    _project(db, "Beta", "/srv/beta")
    store_health_snapshot(alpha.id, "healthy")
    _login(client, app_settings)

    by_name = client.get("/projects?name=alp").json()
    assert [item["name"] for item in by_name] == ["Alpha"]

    by_status = client.get("/projects?status=healthy").json()
    assert [item["name"] for item in by_status] == ["Alpha"]

    unknown = client.get("/projects?status=unknown").json()
    assert [item["name"] for item in unknown] == ["Beta"]


def test_project_list_paginates(client, db, app_settings) -> None:
    for name in ("Alpha", "Beta", "Gamma"):
        _project(db, name, f"/srv/{name.lower()}")
    _login(client, app_settings)

    first = client.get("/projects?per_page=2&page=1").json()
    second = client.get("/projects?per_page=2&page=2").json()
    assert [item["name"] for item in first] == ["Alpha", "Beta"]
    assert [item["name"] for item in second] == ["Gamma"]


def test_project_list_rejects_invalid_pagination(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/projects?per_page=500").status_code == 422


def test_project_detail_counts_related_records(client, db, app_settings) -> None:
    project = _project(db)
    repo.upsert_milestone(db, project.id, "Ship", None, "open", None)
    repo.upsert_milestone(db, project.id, "Document", None, "completed", None)
    repo.upsert_evidence(db, project.id, None, "Proof", "a" * 64, 0.9, "claim")
    repo.upsert_discord_mapping(db, project.id, 1, 2, "next")
    store_health_snapshot(project.id, "healthy")
    _login(client, app_settings)

    response = client.get(f"/projects/{project.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Alpha"
    assert body["status"] == "healthy"
    assert body["milestone_count"] == 2
    assert body["evidence_count"] == 1
    assert body["discord_mappings"] == 1
    assert body["health_freshness"] == "fresh"
    assert body["created_at_utc"].endswith("Z")


def test_project_detail_without_snapshot(client, db, app_settings) -> None:
    project = _project(db)
    _login(client, app_settings)

    body = client.get(f"/projects/{project.id}").json()
    assert body["status"] == "unknown"
    assert body["health_freshness"] == "unknown"


def test_project_detail_missing_returns_404(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/projects/9999").status_code == 404


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def test_milestones_are_listed(client, db, app_settings) -> None:
    project = _project(db)
    repo.upsert_milestone(db, project.id, "Ship", None, "in_progress", "2026-12-01")
    _login(client, app_settings)

    response = client.get(f"/projects/{project.id}/milestones")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Ship"
    assert body[0]["status"] == "in_progress"
    assert body[0]["target_date"] == "2026-12-01"


def test_milestone_with_unknown_status_defaults_to_open(client, db, app_settings) -> None:
    project = _project(db)
    db.execute(
        "INSERT INTO milestones "
        "(project_id, title, description, status, target_date_utc, created_at_utc) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project.id, "Odd", None, "weird-status", None, "2026-01-01T00:00:00Z"),
    )
    _login(client, app_settings)

    body = client.get(f"/projects/{project.id}/milestones").json()
    assert body[0]["status"] == "open"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_list_and_detail(client, db, app_settings) -> None:
    project = _project(db)
    evidence = repo.upsert_evidence(db, project.id, None, "Proof", "b" * 64, 0.8, "claim")
    _login(client, app_settings)

    listing = client.get(f"/projects/{project.id}/evidence").json()
    assert len(listing) == 1
    assert listing[0]["id"] == evidence.id
    assert listing[0]["confidence"] == 0.8
    assert listing[0]["is_stale"] is False

    detail = client.get(f"/projects/{project.id}/evidence/{evidence.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Proof"
    assert body["claim"] == "claim"
    assert body["relevance_score"] == 0.0  # unranked by default


def test_evidence_detail_missing_returns_404(client, db, app_settings) -> None:
    project = _project(db)
    _login(client, app_settings)
    assert client.get(f"/projects/{project.id}/evidence/999").status_code == 404


def test_evidence_must_belong_to_the_project(client, db, app_settings) -> None:
    first = _project(db, "Alpha", "/srv/alpha")
    second = _project(db, "Beta", "/srv/beta")
    evidence = repo.upsert_evidence(db, first.id, None, "Proof", "c" * 64, 1.0, None)
    _login(client, app_settings)

    assert client.get(f"/projects/{second.id}/evidence/{evidence.id}").status_code == 404


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------


def test_recent_activity_lists_notes(client, db, app_settings) -> None:
    project = _project(db)
    repo.upsert_note(db, project.id, 123, "first note")
    repo.upsert_note(db, project.id, 123, "second note")
    _login(client, app_settings)

    response = client.get("/activity/recent")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    titles = [entry["title"] for entry in body]
    assert set(titles) == {"first note", "second note"}
    assert body[0]["type"] == "note"
    assert body[0]["actor"] == "<@123>"
    assert body[0]["occurred_at_utc"].endswith("Z")


def test_recent_activity_without_notes(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/activity/recent").json() == []


def test_recent_activity_handles_missing_user(client, db, app_settings) -> None:
    project = _project(db)
    repo.upsert_note(db, project.id, None, "system note")
    _login(client, app_settings)

    body = client.get("/activity/recent").json()
    assert body[0]["actor"] == "system"


def test_recent_activity_respects_page_size(client, db, app_settings) -> None:
    project = _project(db)
    for index in range(3):
        repo.upsert_note(db, project.id, None, f"note {index}")
    _login(client, app_settings)

    assert len(client.get("/activity/recent?per_page=2").json()) == 2


# ---------------------------------------------------------------------------
# Catalog and research
# ---------------------------------------------------------------------------


def _catalog_project(db, name: str = "Catalog Alpha"):
    return repo.upsert_catalog_project(
        db,
        catalog_key="a" * 64,
        name=name,
        description="Catalog description",
        local_path="C:\\Projects\\Alpha",
        repo_url="https://example.com/alpha",
        tech_stack_json='["Python", "FastAPI"]',
        category="01 - High Priority Projects",
        priority="high",
        catalog_status="active",
        last_activity_utc="2026-10-20T00:00:00Z",
        metadata_json='{"relative_path": "Alpha"}',
        monitored=False,
    )


def _research_job(db, project_id, question="How does research work?"):
    job = repo.upsert_research_job(db, project_id, 1, question, scope="both", provider="tavily")
    repo.upsert_research_source(
        db,
        job.id,
        "Example source",
        "https://example.com/source",
        "web",
        "b" * 64,
        snippet="A source snippet",
        relevance_score=0.75,
        source_ref="https://example.com/source",
    )
    repo.upsert_research_report(db, job.id, "# Report\n\nBody", citation_count=1)
    repo.complete_research_job(db, job.id, status="completed", result_summary="1 source")
    db.commit()
    return job


def test_project_list_includes_catalog_metadata(client, db, app_settings) -> None:
    project = _catalog_project(db)
    repo.upsert_work_item(db, project.id, "commit", "A commit", source="git")
    _login(client, app_settings)

    body = client.get("/projects").json()[0]
    assert body["description"] == "Catalog description"
    assert body["catalog_status"] == "active"
    assert body["category"] == "01 - High Priority Projects"
    assert body["priority"] == "high"
    assert body["tech_stack"] == ["Python", "FastAPI"]
    assert body["source"] == "catalog"
    assert body["monitored"] is False
    assert body["last_activity_utc"] == "2026-10-20T00:00:00Z"
    assert body["work_item_count"] == 1
    assert body["repo_url"] == "https://example.com/alpha"


def test_project_detail_includes_recent_work_and_research(client, db, app_settings) -> None:
    project = _project(db)
    repo.upsert_work_item(db, project.id, "commit", "A commit", body="Body", source="git")
    job = _research_job(db, project.id)
    _login(client, app_settings)

    body = client.get(f"/projects/{project.id}").json()
    assert body["work_item_count"] == 1
    assert body["research_count"] == 1
    assert body["recent_work"][0]["title"] == "A commit"
    assert body["recent_work"][0]["body"] == "Body"
    assert body["recent_research"][0]["id"] == job.id
    assert body["recent_research"][0]["project_name"] == "Alpha"
    assert body["recent_research"][0]["source_count"] == 1
    assert body["recent_research"][0]["result_summary"] == "1 source"


def test_research_list_scopes_pagination_and_detail(client, db, app_settings) -> None:
    project = _project(db)
    job = _research_job(db, project.id)
    global_job = repo.upsert_research_job(db, None, None, "Global question", scope="local")
    repo.upsert_research_report(db, global_job.id, "Global report", citation_count=0)
    repo.complete_research_job(db, global_job.id, status="completed")
    db.commit()
    _login(client, app_settings)

    all_jobs = client.get("/research").json()
    assert {item["id"] for item in all_jobs} == {job.id, global_job.id}
    scoped = client.get(f"/research?project_id={project.id}").json()
    assert [item["id"] for item in scoped] == [job.id]
    assert scoped[0]["project_name"] == "Alpha"
    assert scoped[0]["source_count"] == 1
    page = client.get("/research?per_page=1&page=2").json()
    assert len(page) == 1

    detail = client.get(f"/research/{job.id}").json()
    assert detail["report_text"] == "# Report\n\nBody"
    assert detail["report_generated_at_utc"].endswith("Z")
    assert detail["source_count"] == 1
    assert detail["sources"][0]["title"] == "Example source"
    assert detail["sources"][0]["url"] == "https://example.com/source"
    assert detail["sources"][0]["relevance_score"] == 0.75
    assert detail["sources"][0]["source_ref"] == "https://example.com/source"

    global_detail = client.get(f"/research/{global_job.id}").json()
    assert global_detail["project_id"] is None
    assert global_detail["project_name"] is None
    assert global_detail["report_text"] == "Global report"


def test_research_detail_missing_returns_404(client, app_settings) -> None:
    _login(client, app_settings)
    assert client.get("/research/9999").status_code == 404


def test_catalog_summary(client, db, app_settings) -> None:
    project = _catalog_project(db)
    repo.upsert_work_item(db, project.id, "commit", "A commit")
    job = repo.upsert_research_job(db, project.id, 1, "Question")
    repo.record_catalog_import(
        db,
        source_name="catalog.json",
        source_checksum="c" * 64,
        project_count=1,
        work_item_count=1,
        metadata_json='{"root": "C:\\\\Projects"}',
    )
    db.commit()
    _login(client, app_settings)

    body = client.get("/catalog/summary").json()
    assert body["project_count"] == 1
    assert body["monitored_count"] == 0
    assert body["catalog_count"] == 1
    assert body["active_count"] == 1
    assert body["work_item_count"] == 1
    assert body["research_job_count"] == 1
    assert body["categories"] == ["01 - High Priority Projects"]
    assert body["last_import_at_utc"].endswith("Z")
    assert job.id


def test_catalog_and_research_endpoints_require_auth(client) -> None:
    for path in ("/research", "/research/1", "/catalog/summary"):
        assert client.get(path).status_code == 401, path


def test_health_reports_research_configuration(client, monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("RESEARCH_API_KEY", "test-key")
    body = client.get("/health").json()
    assert body["research_configured"] is True


def test_catalog_summary_without_import(client, app_settings) -> None:
    _login(client, app_settings)
    body = client.get("/catalog/summary").json()
    assert body["project_count"] == 0
    assert body["last_import_at_utc"] is None
    assert body["categories"] == []
