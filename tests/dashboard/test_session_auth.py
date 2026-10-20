"""Dashboard owner-session authentication tests (Phase 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_intelligence.dashboard import session_auth
from project_intelligence.dashboard.session_auth import SessionAuthError


def test_issue_and_verify_roundtrip(app_settings) -> None:
    token, expires = session_auth.issue_session_token(app_settings)

    assert token.startswith("v1.")
    assert len(token.split(".")) == 4
    assert expires > 0
    assert session_auth.verify_session_token(token, app_settings) is True


def test_tampered_signature_is_rejected(app_settings) -> None:
    token, _ = session_auth.issue_session_token(app_settings)
    last = token[-1]
    replacement = "0" if last != "0" else "1"
    tampered = token[:-1] + replacement

    assert session_auth.verify_session_token(tampered, app_settings) is False


def test_expired_token_is_rejected(app_settings, monkeypatch) -> None:
    now = [1_000_000.0]
    monkeypatch.setattr(session_auth.time, "time", lambda: now[0])

    token, expires = session_auth.issue_session_token(app_settings)
    assert session_auth.verify_session_token(token, app_settings) is True

    now[0] = expires + 1
    assert session_auth.verify_session_token(token, app_settings) is False


def test_overlong_lifetime_is_rejected_even_when_signed(app_settings) -> None:
    secret = session_auth.load_owner_secret(app_settings)
    now = int(session_auth.time.time())
    expires = now + session_auth.SESSION_TTL_SECONDS + 600
    payload = f"v1|{expires}|nonce"
    token = f"v1.{expires}.nonce.{session_auth._sign(secret, payload)}"

    assert session_auth.verify_session_token(token, app_settings) is False


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "v1",
        "v1.1.2",
        "v2.9999999999.nonce.deadbeef",
        "v1.not-a-number.nonce.deadbeef",
        "v1.9999999999.nonce.not-a-hex-signature",
    ],
)
def test_malformed_tokens_are_rejected(app_settings, token) -> None:
    assert session_auth.verify_session_token(token, app_settings) is False


def test_token_is_rejected_after_secret_rotation(app_settings) -> None:
    token, _ = session_auth.issue_session_token(app_settings)
    assert session_auth.verify_session_token(token, app_settings) is True

    Path(app_settings.dashboard_session_secret_file).write_text("r" * 64, encoding="utf-8")
    assert session_auth.verify_session_token(token, app_settings) is False


def test_token_is_rejected_when_secret_file_disappears(app_settings) -> None:
    token, _ = session_auth.issue_session_token(app_settings)
    Path(app_settings.dashboard_session_secret_file).unlink()
    assert session_auth.verify_session_token(token, app_settings) is False


# ---------------------------------------------------------------------------
# Secret loading
# ---------------------------------------------------------------------------


def test_load_owner_secret_reads_and_strips_file(app_settings) -> None:
    secret = session_auth.load_owner_secret(app_settings)
    assert secret == b"s" * 64


def test_missing_secret_file_is_an_error(app_settings) -> None:
    app_settings.dashboard_session_secret_file = Path("does-not-exist")
    with pytest.raises(SessionAuthError, match="unreadable"):
        session_auth.load_owner_secret(app_settings)


def test_unconfigured_secret_file_is_an_error(make_settings) -> None:
    with pytest.raises(SessionAuthError, match="not configured"):
        session_auth.load_owner_secret(make_settings(dashboard_session_secret_file=None))


def test_short_secret_is_rejected(make_settings, tmp_path: Path) -> None:
    secret_file = tmp_path / "short"
    secret_file.write_text("too-short", encoding="utf-8")
    with pytest.raises(SessionAuthError, match="too short"):
        session_auth.load_owner_secret(make_settings(dashboard_session_secret_file=secret_file))


# ---------------------------------------------------------------------------
# Secret comparison
# ---------------------------------------------------------------------------


def test_verify_owner_secret(app_settings) -> None:
    assert session_auth.verify_owner_secret("s" * 64, app_settings) is True
    assert session_auth.verify_owner_secret("s" * 63, app_settings) is False
    assert session_auth.verify_owner_secret("", app_settings) is False
    assert session_auth.verify_owner_secret("wrong", app_settings) is False


def test_verify_owner_secret_without_configuration(make_settings) -> None:
    assert (
        session_auth.verify_owner_secret(
            "anything", make_settings(dashboard_session_secret_file=None)
        )
        is False
    )


# ---------------------------------------------------------------------------
# Owner context and cookie settings
# ---------------------------------------------------------------------------


def test_owner_context_is_an_owner(app_settings) -> None:
    ctx = session_auth.owner_auth_context(app_settings)
    assert ctx.auth_via == "owner_session"
    assert ctx.discord_user_id == app_settings.discord_owner_user_ids[0]
    assert ctx.is_owner(app_settings) is True


def test_owner_context_without_owner_ids(make_settings) -> None:
    ctx = session_auth.owner_auth_context(make_settings(discord_owner_user_ids=[]))
    assert ctx.discord_user_id == 0


def test_cookie_settings_in_development(app_settings) -> None:
    settings = session_auth.get_cookie_security_settings(app_settings)
    assert settings["httponly"] is True
    assert settings["secure"] is False  # testing/development runs over loopback HTTP
    assert settings["samesite"] == "strict"
    assert settings["max_age"] == session_auth.SESSION_TTL_SECONDS
    assert settings["path"] == "/"


def test_cookie_settings_in_production(make_settings, tmp_path: Path) -> None:
    production = make_settings(
        app_env="production",
        data_dir=tmp_path,
        database_path=tmp_path / "db.sqlite3",
        dashboard_session_secret_file=tmp_path / "secret",
    )
    settings = session_auth.get_cookie_security_settings(production)
    assert settings["secure"] is True


# ---------------------------------------------------------------------------
# Legacy helpers
# ---------------------------------------------------------------------------


def test_validate_session_delegates_to_verifier(app_settings) -> None:
    token, _ = session_auth.issue_session_token(app_settings)
    assert session_auth.validate_session(token, settings=app_settings) is True
    assert session_auth.validate_session(None, settings=app_settings) is False


def test_hash_session_token_is_stable() -> None:
    assert session_auth.hash_session_token("abc") == session_auth.hash_session_token("abc")
    assert session_auth.hash_session_token("abc") != session_auth.hash_session_token("abd")


def test_csrf_helpers() -> None:
    token = session_auth.generate_csrf_token()
    assert session_auth.verify_csrf_token(token, token) is True
    assert session_auth.verify_csrf_token(token, token + "x") is False


def test_generated_session_tokens_are_unique() -> None:
    assert session_auth.generate_session_token() != session_auth.generate_session_token()
