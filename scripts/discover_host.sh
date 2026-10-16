#!/usr/bin/env bash
# Read-only host discovery for the discord-project-intelligence deployment target.
# Purpose: Phase 1 inventory of the Ubuntu homelab ("homelab3013").
#
# SAFETY: This script only reads information. It does not install, start, stop,
# restart, or modify anything, and it requires no root. Run as your normal user:
#
#   bash discover_host.sh
#
# Review the output for anything you consider sensitive (device names, local
# paths, listening ports) before sharing it. The script reads no credentials
# and contains no secrets by design.

set -u

section() { printf '\n===== %s =====\n' "$1"; }

section "Host and OS"
hostname
uname -srm
cat /etc/os-release 2>/dev/null | head -n 8
ip -brief address 2>/dev/null | head -n 20

section "Tooling versions"
python3 --version 2>&1
git --version 2>&1
systemctl --version 2>/dev/null | head -n 1
command -v docker >/dev/null 2>&1 && docker --version 2>&1 || echo "docker: not found"
command -v podman >/dev/null 2>&1 && podman --version 2>&1 || echo "podman: not found"
command -v opencode >/dev/null 2>&1 && opencode --version 2>&1 || echo "opencode: not found"

section "CPU / memory / disk"
nproc
free -h 2>/dev/null
df -h / /home 2>/dev/null

section "Listening sockets (TCP)"
ss -tln 2>/dev/null || netstat -tln 2>/dev/null

section "Running services (first 40)"
systemctl list-units --type=service --state=running --no-pager 2>/dev/null | head -n 40

section "Ollama"
command -v ollama >/dev/null 2>&1 && ollama --version 2>&1 || echo "ollama CLI: not found"
ollama list 2>/dev/null || echo "ollama list: unavailable"
# Local API check (loopback only)
curl -s --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null | head -c 2000
echo

section "Tailscale"
command -v tailscale >/dev/null 2>&1 && tailscale version 2>&1 || echo "tailscale: not found"
tailscale status 2>/dev/null | head -n 25 || echo "tailscale status: unavailable"
echo "--- serve status ---"
tailscale serve status 2>/dev/null || echo "tailscale serve status: unavailable"

section "OpenCode processes"
pgrep -af opencode 2>/dev/null | head -n 10 || echo "no opencode processes found"

echo
echo "Discovery complete. No changes were made."
