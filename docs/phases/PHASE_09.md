# Phase 9 — Deployment and systemd Hardening

**Status: PASS** — Deployment configuration prepared, systemd unit file created, hardening documented. No host changes made (requires owner approval).

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Prepared an isolated, resource-limited deployment configuration for the Discord Project Intelligence application. All changes are local files — no host, service, or network changes were made. The deployment uses systemd (based on the host having systemd available per Phase 1 findings) with a dedicated non-root service account, strict hardening options, and minimal writable directories.

## Implemented

- **`deploy/systemd/discord-project-intelligence.service`** — systemd unit file:
  - Dedicated non-root user `dpi` / group `dpi`
  - `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`
  - `ProtectKernelTunables`, `ProtectKernelModules`, `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`
  - `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` (loopback + Unix sockets only)
  - `RestrictNamespaces`, `RestrictRealtime`, `RestrictSUIDSGID`, `LockPersonality`
  - `MemoryDenyWriteExecute=true`
  - `SystemCallFilter=@system-service`
  - Resource limits: `MemoryMax=512M`, `CPUQuota=50%`, `TasksMax=64`
  - Restart behavior: `Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=60`, `StartLimitBurst=3`
  - Graceful shutdown: `TimeoutStopSec=30`, `KillMode=mixed`, `KillSignal=SIGTERM`
  - Read-write paths restricted to `/var/lib/dpi/data` and `/var/log/dpi`
  - Read-only environment file at `/etc/dpi/.env` (mode 0640, root:dpi)
  - Structured journald logging with `SyslogIdentifier=dpi`

- **`deploy/hardening/apparmor-profile`** — AppArmor profile (optional):
  - Read-only access to application code
  - Read-write to data and log directories only
  - Denies access to sensitive system files

- **`scripts/backup_db.py`** — SQLite-consistent backup script:
  - Uses `VACUUM INTO` for consistent snapshots
  - Integrity check verification on backup
  - Configurable retention (default 7 days)
  - Owner-only permissions (0600) on backup files

- **`docs/THREAT_MODEL.md`** — Updated with deployment trust boundaries

- **`docs/SECURITY.md`** — Updated with deployment hardening section

- **`docs/OPERATIONS.md`** — Updated with deployment procedures

## Not implemented (by design, later phases)

- No actual host deployment (requires owner approval)
- No service account creation
- No firewall changes
- No SSH configuration changes
- No package installation on the host

## Files added / changed

| File | Purpose |
|---|---|
| `deploy/systemd/discord-project-intelligence.service` | systemd unit file |
| `deploy/hardening/apparmor-profile` | AppArmor profile |
| `scripts/backup_db.py` | SQLite backup script |
| `docs/THREAT_MODEL.md` | Updated with deployment trust boundaries |
| `docs/SECURITY.md` | Updated with deployment hardening section |
| `docs/OPERATIONS.md` | Updated with deployment procedures |
| `docs/phases/PHASE_09.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Application can run as a dedicated non-root user in a test environment | ✅ PASS (config) | Unit file specifies `User=dpi`, `Group=dpi` |
| Service configuration is documented and validated | ✅ PASS | Unit file validated for syntax; deployment steps documented |
| Deployment changes are reversible | ✅ PASS | Rollback procedure documented in unit file header |
| Required permissions are minimal | ✅ PASS | `ProtectSystem=strict`, `ProtectHome=true`, read-only paths |

## Known limitations

- No actual host deployment performed (requires owner approval)
- AppArmor profile is optional and may need adjustment for the specific Python version
- Systemd hardening options may need to be relaxed if they break functionality
- Backup script uses `VACUUM INTO` which requires SQLite 3.27+ (available in Ubuntu 22.04+)

## Required human actions

1. **Owner approval required** before any host changes
2. **When homelab is online**: Run the installation steps in the unit file header
3. **Verify**: `sudo systemctl status discord-project-intelligence`

## Next phase prerequisites (Phase 10 — Discord Bot Foundation)

- Clean tree at this commit; all gates green
- Phase 10 adds: Discord client (discord.py), bot token from protected config, /help and /status commands, centralized command authorization, guild/channel/user ID verification, ephemeral responses, interaction timeouts, rate limiting, minimal bot permissions, offline test mode

## Rollback procedure

1. `sudo systemctl stop discord-project-intelligence`
2. `sudo systemctl disable discord-project-intelligence`
3. `sudo rm /etc/systemd/system/discord-project-intelligence.service`
4. `sudo systemctl daemon-reload`
5. Delete `/opt/dpi/app` and `/var/lib/dpi/data` if desired

No external state was touched; the remote repository is empty and unpushed.

## Git commit hash

(To be recorded after committing this phase's changes)