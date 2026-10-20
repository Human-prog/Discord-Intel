# Operations — Discord Project Intelligence

**Status:** Phase 20 (2026-10-20). The dashboard runs as a hardened systemd service on `home3013`; the Discord bot has a separate hardened unit and is enabled once `/etc/dpi/.env` carries a token, owner IDs, and allowlists. Live GitHub, Ollama, and OpenCode integrations remain opt-in and disabled by default. See `docs/DISCORD_SETUP.md`.

## 1. Environments

| Environment | Identity | State |
|---|---|---|
| Development | Windows 11 workstation `DESKTOP-A32JB4P` | Active |
| Deployment | Ubuntu homelab `home3013` — LAN `192.168.1.186`, tailnet `100.72.17.90` | Dashboard service active |

### Current deployment (verified 2026-10-20)

| Item | Value |
|---|---|
| Dashboard service | `discord-project-intelligence.service` (systemd, `Restart=on-failure`) |
| Discord bot service | `discord-project-intelligence-bot.service` (systemd, `Restart=on-failure`) |
| Service account | `dpi` |
| Application | `/opt/dpi/app` |
| Configuration | `/etc/dpi/.env` (mode `0640`, `root:dpi`) |
| Dashboard session secret | `/etc/dpi/session_secret` (mode `0640`, `root:dpi`) |
| Database | `/var/lib/dpi/data/db.sqlite3` |
| Listener | `127.0.0.1:8765` only |
| Tailnet URL | `https://home3013.tail53635c.ts.net` (Tailscale Serve → loopback) |
| Dashboard logs | `journalctl -u discord-project-intelligence` |
| Bot logs | `journalctl -u discord-project-intelligence-bot` |

Health check from the host:

```bash
curl -fsS http://127.0.0.1:8765/health
```

Dashboard sign-in uses the contents of `/etc/dpi/session_secret` as the owner
secret. Rotating that file invalidates every existing session. Never enable
Funnel, port forwarding, or a public reverse proxy, and preserve the existing
OpenCode Serve route.

## 2. Development machine inventory (observed facts, 2026-10-15)

| Item | Observed value |
|---|---|
| OS | Windows 11 Enterprise 10.0.22621 64-bit |
| RAM | 15.3 GB |
| Disk (C:) | 277.8 GB free |
| Python | 3.12.10 (`C:\Program Files\Python312`); launcher also sees 3.11, 3.12, 3.13, 3.14 |
| Git | 2.55.0.windows.5 |
| GitHub CLI | Installed at `C:\Program Files\GitHub CLI\gh.exe`; **not authenticated** |
| SSH client | Windows OpenSSH present |
| Tailscale | Installed and running; dev machine IP `100.94.150.67` |
| Tailnet membership | Currently lists only `desktop-a32jb4p` and `iphone-15` — no homelab device |
| Docker | Docker Desktop present (CLI available) |
| Other | node/npm present; `uv` and `pipx` **not installed** |
| LAN | Wi-Fi `192.168.1.19/24` |

Repository identity used in existing local repos (from `Modelbridge` history): `Human-prog <creekcraig77@gmail.com>`. This identity is used for commits in this repository (repo-local config if no global identity is set).

## 3. Homelab inventory (verified 2026-10-20)

`home3013` is online and reachable on the tailnet (`100.72.17.90`) and LAN
(`192.168.1.186`). Ubuntu, Python 3.14.4, dedicated `dpi` service account,
dashboard service enabled and active, Tailscale Serve publishing
`https://home3013.tail53635c.ts.net` → `127.0.0.1:8765`. The existing OpenCode
Serve route is unchanged. The read-only discovery script remains available for
periodic re-inventory:

```bash
scp scripts/discover_host.sh <user>@192.168.1.187:~/
ssh <user>@192.168.1.187 'bash ~/discover_host.sh' | tee discover_host_output.txt
```

It inventories: OS/kernel, Python/git/systemd/docker/podman/opencode versions, CPU/memory/disk, listening TCP sockets, running services, Ollama version + model list + local API tags, Tailscale version/status/serve status, and OpenCode processes. It reads no credentials. Review output for anything you consider sensitive before sharing; then provide the output to continue host-related phases (8, 9, 12, 14, 17).

Manual equivalent (if you prefer to run commands yourself):

```bash
hostname; uname -srm; cat /etc/os-release | head -8
python3 --version; git --version; systemctl --version | head -1
docker --version 2>/dev/null; podman --version 2>/dev/null
nproc; free -h; df -h /
ss -tln
systemctl list-units --type=service --state=running --no-pager | head -40
ollama --version; ollama list; curl -s --max-time 3 http://127.0.0.1:11434/api/tags
tailscale version; tailscale status; tailscale serve status
pgrep -af opencode
```

## 4. Git remote and pushes (active)

`origin` is configured as `https://github.com/Human-prog/Discord-Intel` (private).
`main` is pushed and `gh` is authenticated as `Human-prog`. Pushing remains an
owner-approved action; never force-push or rewrite shared history.

If the CLI session expires, re-authenticate:

Option A (GitHub CLI):

```bash
gh auth login          # GitHub.com → HTTPS → login with a browser
git push -u origin main
```

Option B (credential manager / PAT): create a fine-grained token scoped to only this repository with the minimum permissions needed to push, then push and let Git Credential Manager prompt for it. **Never paste tokens into chat, files, or command lines; never commit them.** Verify the remote is private after pushing.

## 5. Development workflow (Phase 3+)

```powershell
python -m venv .venv                                      # once
.venv\Scripts\python -m pip install -e ".[dev]"           # install (pins: requirements.lock)
.venv\Scripts\python -m pytest -q --cov                   # tests + coverage gate
.venv\Scripts\ruff.exe check .                            # lint
.venv\Scripts\ruff.exe format --check .                   # formatting
.venv\Scripts\python -m mypy .                            # type check
.venv\Scripts\pip-audit.exe --progress-spinner off        # dependency audit
.venv\Scripts\python scripts\scan_secrets.py              # secret scan
.venv\Scripts\python scripts\validate_config.py           # non-destructive config check
```

On Linux, use `.venv/bin/python` and call `ruff` / `pip-audit` directly. All of
these gates also run in CI (`.github/workflows/ci.yml`, `ubuntu-latest`,
installing from `requirements.lock`; least-privilege `contents: read`). CI runs
on every push to `main` and on pull requests. Configuration is environment-based
with an optional `.env` file (copy `.env.example`); diagnostics never print
secret values. The dashboard is managed by
`discord-project-intelligence.service`; after deploying, restart it with
`sudo systemctl restart discord-project-intelligence` and re-check `/health`.

### Updating the deployment

The server has no GitHub credentials by design, so updates move as a verified
Git bundle over Taildrop, never `git pull`.

On the development machine:

```powershell
git -C "C:\Users\Arega\Desktop\Projects\Discord Project Intelligence" bundle create "$env:TEMP\dpi-main.bundle" main
tailscale file cp "$env:TEMP\dpi-main.bundle" home3013:
```

On `home3013`:

```bash
sudo systemctl stop discord-project-intelligence-bot discord-project-intelligence
sudo tailscale file get /tmp
sudo chown dpi:dpi /tmp/dpi-main.bundle

cd /opt/dpi/app
sudo -u dpi git fetch /tmp/dpi-main.bundle main
sudo -u dpi git merge --ff-only FETCH_HEAD
sudo -u dpi /opt/dpi/app/.venv/bin/pip install -r /opt/dpi/app/requirements.lock
sudo -u dpi /opt/dpi/app/.venv/bin/pip install --no-deps -e /opt/dpi/app

sudo systemctl start discord-project-intelligence
sudo systemctl start discord-project-intelligence-bot   # if configured
curl -fsS http://127.0.0.1:8765/health
```

Before the first bundle-based update on a checkout with local edits, park them
with `sudo -u dpi git -C /opt/dpi/app stash push -u -m "pre-update"` and
re-apply deliberately if still needed.

Migrations apply automatically on startup. Confirm the schema version and the
`/health` payload, then sign in through the tailnet URL. If a service fails to
start, inspect `journalctl -u <unit>` and roll back to the previous commit
(e.g. `sudo -u dpi git -C /opt/dpi/app reset --hard <previous-sha>`).

## 6. Pending manual actions (tracked)

- [x] Push the initial commit to GitHub — done 2026-10-20 (`Human-prog/Discord-Intel`)
- [x] Bring the homelab online and run `scripts/discover_host.sh` — host now reachable
- [x] Confirm homelab identity — `home3013` at `192.168.1.186` / `100.72.17.90`
- [x] Dependency/lock tooling — `requirements.lock` + editable install; CI installs the lock
- [ ] Configure the live Discord bot per `docs/DISCORD_SETUP.md` (token, owner IDs, guild/channel allowlists, allowed roots), then `sudo systemctl enable --now discord-project-intelligence-bot`
- [ ] Optional: configure GitHub read-only credentials (App preferred, fine-grained token fallback)
- [ ] Optional: install/pull the Ollama model used for local analysis
- [ ] Rotate `/etc/dpi/session_secret` periodically (invalidates all dashboard sessions)

## 7. Rollback procedures

**Current deployment (dashboard):** stop and disable
`discord-project-intelligence.service`, remove the unit, and `git revert` the
release commits. If a release changed persisted data, restore the pre-release
backup from `scripts/backup_db.py` following `docs/BACKUP_RECOVERY.md`. Never
modify the Tailscale Serve route as part of an application rollback; the
existing OpenCode route must remain intact. Rotating
`/etc/dpi/session_secret` is a safe last resort for suspected session compromise.

Historical Phase 1–3 rollback notes remain in the phase reports. To revert a
decision documented in `docs/ARCHITECTURE.md` §7, edit the decision log with
owner approval.

## 8. Safety rules for operating this project

- Never enable Tailscale Funnel, router port forwarding, or public listeners.
- Never modify the existing OpenCode Serve route without inspecting and preserving it first; changes require owner approval.
- Never install packages as root or modify host services without a documented proposal and owner approval.
- Never commit secrets; keep `.env` files out of the repository with restricted permissions.
- Keep the service data directory separate from source; backups get the same protection as production data.
