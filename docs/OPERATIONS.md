# Operations — Discord Project Intelligence

**Status:** Phase 1 (2026-10-15). Nothing runs yet — no application code exists. This manual grows each phase: configuration (Phase 2), tests/CI (Phase 3), dashboard (Phase 7+), deployment (Phase 9), release procedures (Phase 20).

## 1. Environments

| Environment | Identity | State at bootstrap |
|---|---|---|
| Development | Windows 11 workstation `DESKTOP-A32JB4P` | Active |
| Deployment target | Ubuntu homelab `homelab3013` | Powered off (owner decision); host discovery deferred |

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

## 3. Homelab discovery (deferred — host intentionally off)

Observed at bootstrap: `homelab3013` does not resolve from the dev machine; no SSH config entry exists; `192.168.1.187` (the only host in the local SSH `known_hosts`, one entry, likely the homelab) did not answer ICMP or SSH port 22 — consistent with the host being powered off. **Assumption to confirm when online:** `192.168.1.187` is `homelab3013`.

When the host is online, run the read-only discovery script **as a normal user** (no root required, makes no changes):

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

## 4. Git remote and first push (pending owner action)

`origin` is configured as `https://github.com/Human-prog/Discord-Intel` (private, empty). **Nothing has been pushed** — pushing requires GitHub authentication that is not configured on this machine (`gh` is logged out).

Option A (recommended — GitHub CLI):

```bash
gh auth login          # GitHub.com → HTTPS → login with a browser
git push -u origin main
```

Option B (credential manager / PAT): create a fine-grained token scoped to only this repository with the minimum permissions needed to push, then push and let Git Credential Manager prompt for it. **Never paste tokens into chat, files, or command lines; never commit them.** Verify the remote is private after pushing.

## 5. Development workflow (Phase 2+)

```powershell
python -m venv .venv                                      # once
.venv\Scripts\python -m pip install -e ".[dev]"           # install (pins: requirements.lock)
.venv\Scripts\python -m pytest                            # test suite
.venv\Scripts\python scripts\validate_config.py           # non-destructive config check
```

On Linux, use `.venv/bin/python`. Configuration is environment-based with an optional `.env` file (copy `.env.example`); diagnostics never print secret values. There is still no long-running service to start — the dashboard arrives in Phase 7 and systemd units in Phase 9.

## 6. Pending manual actions (tracked)

- [ ] Push the initial commit to GitHub — owner (needs `gh auth login` or PAT; see §4)
- [ ] When the homelab is online: run `scripts/discover_host.sh` and return the output — owner
- [ ] Confirm homelab identity: is `192.168.1.187` = `homelab3013`? — owner
- [x] Dependency/lock tooling decided (Phase 2): venv + editable install, third-party pins in `requirements.lock` (pip freeze). Revisit only if Linux CI reproducibility needs more (Phase 3).

## 7. Rollback procedures

**Phases 1–2 (current):** Bootstrap rollback = delete the repository folder; nothing outside it was changed. Configuration rollback = `git revert` the Phase 2 commit(s) (code, tests, and docs are additive; no persisted data exists yet). The remote remains empty until pushed, so no remote rollback is needed. To revert a decision documented in `docs/ARCHITECTURE.md` §7, edit the decision log with owner approval.

Future phases add per-phase rollback sections here and in their phase reports.

## 8. Safety rules for operating this project

- Never enable Tailscale Funnel, router port forwarding, or public listeners.
- Never modify the existing OpenCode Serve route without inspecting and preserving it first; changes require owner approval.
- Never install packages as root or modify host services without a documented proposal and owner approval.
- Never commit secrets; keep `.env` files out of the repository with restricted permissions.
- Keep the service data directory separate from source; backups get the same protection as production data.
