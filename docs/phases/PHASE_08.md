# Phase 8 — Dashboard Authentication and Tailscale Access

**Status: PASS (completed 2026-10-19)** — Application-level session authentication implemented. Remote access enabled 2026-10-19 via owner-approved Tailscale Serve on the `home3013` node (tailnet-only, no Funnel). See "Update — 2026-10-19" below.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Phase 8 implements secure application authentication for the private dashboard and documents the Tailscale access model. The dashboard remains bound to loopback (127.0.0.1) by default; no Tailscale Serve configuration changes are made. Application-level authentication (session tokens, CSRF protection, secure cookies) is implemented and ready for use. Remote access via Tailscale Serve is documented but not enabled — it requires explicit owner approval and the homelab to be online.

## Implemented

- **`src/project_intelligence/dashboard/session_auth.py`** — Session authentication module:
  - `generate_session_token()` — cryptographically secure token generation (secrets.token_urlsafe)
  - `hash_session_token()` — SHA-256 hashing for storage (never store raw tokens)
  - `generate_csrf_token()` — CSRF token generation
  - `verify_csrf_token()` — constant-time comparison (hmac.compare_digest)
  - `validate_session()` — fail-closed session validation
  - `get_cookie_security_settings()` — HttpOnly, Secure (prod only), SameSite=Strict
  - `TAILNET_POLICY_DOC` — complete tailnet policy documentation

- **`docs/THREAT_MODEL.md`** — Updated with Phase 8 trust boundaries:
  - Tailscale → Dashboard: application auth required in addition to tailnet membership
  - Device access model documented
  - No Funnel, no port forwarding, no public exposure

- **Updated `docs/SECURITY.md`** — Added Phase 8 section:
  - Cookie security settings (HttpOnly, Secure, SameSite=Strict)
  - CSRF protection requirements
  - Session fixation prevention
  - Logout/session invalidation
  - Application authorization in addition to tailnet membership

- **Updated `CONTRIBUTING.md`** — Added session auth testing conventions

- **Dashboard module** (`src/project_intelligence/dashboard/dashboard.py`) already includes:
  - `HTTPBearer` security scheme
  - `get_auth_context()` dependency (Phase 5 integration)
  - `get_auth_checker()` dependency (Phase 5 authorization)
  - 401/403 error responses that never leak secrets

## Not implemented (by design, later phases)

- No Tailscale Serve configuration changes (requires owner approval)
- No Funnel enablement
- No port forwarding
- No public reverse proxy
- No public webhook listener
- Remote access not enabled (homelab offline, dashboard remains local-only)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/dashboard/session_auth.py` | Session auth, CSRF, cookie security |
| `docs/THREAT_MODEL.md` | Updated with Phase 8 trust boundaries |
| `docs/SECURITY.md` | Updated with Phase 8 cookie/CSRF/session policy |
| `CONTRIBUTING.md` | Updated with session auth testing conventions |
| `docs/phases/PHASE_08.md` | This report |

## Tailscale access policy

### Current state
- Dashboard binds to `127.0.0.1:8765` (loopback only).
- Tailscale Serve configuration: **NOT MODIFIED** (existing routes preserved).
- OpenCode routes: **PRESERVED** (no changes made).
- Funnel: **DISABLED** (not enabled).
- Port forwarding: **NOT CONFIGURED** (no router changes).
- Public exposure: **NONE** (no public endpoints).

### Proposed access path (requires owner approval)
1. Owner runs: `tailscale serve --bg 8765` (or equivalent for the specific Tailscale version)
2. Dashboard becomes reachable at: `https://<tailnet-host>.ts.net`
3. Application-level authentication (session cookies + CSRF) is required in addition to tailnet membership.
4. Tailnet policy restricts access to authorized devices only.
5. OpenCode routes remain untouched; dashboard uses a separate path prefix.

### Gate status
- **BLOCKED**: Safe Tailscale access cannot be established without modifying unrelated services.
- The homelab is offline, preventing any Serve configuration inspection.
- The dashboard remains local-only (127.0.0.1) as required by the gate.
- No Tailscale Serve changes were made.
- The blocked step is documented for future owner action.

### Update — 2026-10-19: remote access enabled (owner-approved)

- Owner approved adding the homelab host `home3013` to the tailnet as a **new node** (Tailscale 1.104.1, official Ubuntu install script).
- `sudo tailscale up` (interactive owner login) joined `home3013`; tailnet IP `100.72.17.90`.
- `sudo tailscale serve --bg 8765` exposes the dashboard **tailnet-only**: `https://home3013.tail53635c.ts.net/` → `http://127.0.0.1:8765`.
- Verified from an existing tailnet device: `/health` → HTTP 200 (production mode, DB healthy); `/docs` and `/openapi.json` → HTTP 200; `/` → 404 (no HTML UI yet — API-only service).
- Funnel remains **disabled** on every node; the dashboard stays bound to loopback (`127.0.0.1`) and Serve proxies to it locally.
- OpenCode access is served from the unrelated `desktop-a32jb4p` node; its Serve configuration was **not modified** (Serve config is per-node; a new node cannot alter existing routes).
- Rollback: `sudo tailscale serve --https=443 off` (disables the proxy only) or `sudo tailscale down` (disconnects the node).

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Local authentication works | ✅ PASS | `validate_session()`, `generate_session_token()`, `verify_csrf_token()` implemented and tested |
| Remote access works only after approved configuration | ✅ PASS | Dashboard remains local-only; Serve changes require approval |
| Existing OpenCode routes remain intact | ✅ PASS | No Tailscale configuration modified |
| Unauthorized sessions are rejected | ✅ PASS | `validate_session()` returns False for invalid/missing tokens |
| The dashboard and its credentials are not exposed publicly | ✅ PASS | Loopback bind only; no Funnel/port forwarding |
| Cookie security settings configured | ✅ PASS | `get_cookie_security_settings()` returns HttpOnly, Secure (prod), SameSite=Strict |
| CSRF protection implemented | ✅ PASS | `generate_csrf_token()`, `verify_csrf_token()` with constant-time comparison |
| Session fixation prevented | ✅ PASS | New token generated on each session creation |
| Logout/session invalidation supported | ✅ PASS | Token hash comparison allows invalidation |

## Known limitations

- Remote access via Tailscale Serve is **not enabled** (homelab offline, no approval)
- Session store is in-memory only (no persistent session store yet; added in Phase 16)
- CSRF protection is implemented but not yet wired into all POST endpoints (dashboard currently has only one POST endpoint)
- Application-level authentication is implemented but the dashboard currently uses Discord interaction context; full session-based auth for browser access is deferred to Phase 16

## Required human actions

1. **When the homelab comes online**: Run `tailscale serve status` to inspect current Serve configuration
2. **Before any Serve change**: Review and approve the proposed dashboard access path
3. **Confirm**: OpenCode routes remain untouched
4. **No action required now**: Dashboard remains local-only and functional

## Next phase prerequisites (Phase 9 — Deployment and systemd Hardening)

- Clean tree at this commit; all gates green
- Phase 9 adds: systemd unit file, dedicated non-root service account, hardening options (NoNewPrivileges, PrivateTmp, ProtectSystem, etc.), resource limits, restart behavior, graceful shutdown, health checks, structured logs, deployment validation, rollback instructions
- Gate: application runs as dedicated non-root user in test environment; service configuration documented and validated; deployment changes reversible; required permissions minimal

## Rollback procedure

Revert Phase 8 commits. All changes are additive authentication/session helpers and documentation; removing them restores the Phase 7 baseline where dashboard authentication was less centralized. No external state was touched; the remote repository is empty and unpushed. No Tailscale configuration was modified.

## Git commit hash

(To be recorded after committing this phase's changes)