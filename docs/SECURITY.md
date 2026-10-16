# Security

Status: initial version (Phase 3). The formal threat model arrives in Phase 5,
adversarial validation in Phase 18. This page covers the security rules the
project already enforces and the response procedure for accidental secret
exposure.

## 1. Network boundary

- The dashboard binds to loopback only and is reachable remotely solely via
  Tailscale Serve (identity-based, tailnet-only). No Funnel, no port
  forwarding, no public listeners.
- Ollama binds to loopback only; all AI analysis of private data is local.
- No inbound webhooks. GitHub integration (Phase 12) is scheduled read-only
  polling with a fine-grained token or GitHub App.
- Required outbound traffic is limited to: Discord (bot), GitHub API, research
  providers (only when explicitly enabled), PyPI during controlled installs,
  and Tailscale coordination.

## 2. Authentication and authorization (principles)

- Fail closed: anything not explicitly allowed is denied.
- Authorization uses numeric Discord IDs (owner allowlist, guild allowlist),
  checked server-side before any work is performed.
- Owner-only or ephemeral responses for anything sensitive; client-supplied
  values are never trusted.
- Implementation lands in Phase 5 (authorization) and Phase 8 (dashboard auth).

## 3. Secret handling

- Secrets live only in environment variables, `.env` (git-ignored), or
  permission-restricted secret files referenced by path. `.env.example`
  contains placeholders only.
- Secrets never appear in: committed files, logs, diagnostics output, error
  messages, Discord messages, research prompts, phase reports, or CI output.
  Diagnostics print set/unset status only.
- Production configuration refuses placeholder values at startup
  (see `src/project_intelligence/config.py`).

## 4. Secret scanning

`scripts/scan_secrets.py` (backed by
`src/project_intelligence/security/secret_scan.py`) deterministically scans the
tree for credential-shaped strings: GitHub tokens, Discord bot tokens, Slack
tokens, AWS access keys, PEM private-key headers, OpenAI-style keys, bearer
headers, and generic `token/secret/password/api_key` assignments. It reports
file, line, and rule name only - never the matched value. It runs locally
before commits and in CI on every push and pull request.

Test fixtures must construct credential-shaped strings programmatically so the
tree itself stays scanner-clean; a test enforces that property.

## 5. Response to accidental secret exposure

Assume compromise the moment a secret is committed, printed, or pasted.

1. Rotate or revoke the credential immediately. Rotation, not deletion, is
   the primary mitigation.
2. Remove the material from the working tree; find and fix the cause.
3. If it was pushed: treat it as public. Rotate first (step 1). History
   rewriting is destructive and requires explicit owner approval and
   coordination - it is never the only step.
4. Verify: re-run the secret scan, confirm the old credential is revoked, and
   review service audit logs for unexpected use.
5. Record what happened (no secret values in the record): what leaked, where,
   rotation evidence, follow-up actions.
6. Prevent recurrence: extend the scanner rules or convert the incident into a
   test.

## 6. Dependencies and supply chain

- `requirements.lock` pins every dependency version; CI installs from it.
- `pip-audit` runs in CI on every push; advisories must be fixed or explicitly
  documented with owner approval.
- Ruff's `S` (flake8-bandit) rules are enabled for first-party code.

## 7. Reporting

Report vulnerabilities or suspected exposure privately to the repository
owner. Do not open public issues for security matters.
