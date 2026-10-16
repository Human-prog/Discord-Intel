# Master Specification — Discord Project Intelligence

Authoritative requirements for this project. Derived from the owner's master specification provided 2026-10-15. If implementation ever conflicts with this document, stop and reconcile before proceeding; changes to this document require owner review.

**Project working name:** `discord-project-intelligence`
**GitHub remote:** `https://github.com/Human-prog/Discord-Intel` (private)
**Deployment target:** Ubuntu homelab `homelab3013`
**Initial operating mode:** Read-only monitoring, project intelligence, research, and reporting

---

## 1. Mission

Build a private, persistent project-intelligence system on the owner's Ubuntu homelab that tracks projects, understands what has been completed, identifies the next useful steps, researches technical ideas, inspects GitHub activity, and monitors connected services — usable from Discord slash commands and a private mobile-friendly dashboard.

The AI is an analysis and planning component, **not the source of truth**. Repository state, service health, test results, and recorded evidence are authoritative.

### 1.1 Success criteria (release 1)

1. Starts automatically on the homelab and recovers from ordinary process failures.
2. Each configured Discord channel/thread maps to the correct project.
3. Status and next-step output is evidence-backed.
4. GitHub integration is read-only.
5. Research output is source-linked, dated, with verification notes.
6. Dashboard reachable from the owner's authorized devices away from home.
7. Dashboard is **not** reachable from the public internet.
8. Unknown Discord users cannot retrieve private project information or start jobs.
9. The release cannot modify code, run arbitrary shell commands, or execute OpenCode tasks.
10. Automated tests, security checks, logs, backups, documentation, and a reproducible deployment procedure exist.

---

## 2. Security boundary (non-negotiable)

### 2.1 "No outside access"

- Authorized owner devices may reach the dashboard via Tailscale.
- No public internet-facing URL. No router port forwarding. No Tailscale Funnel. No public reverse proxy or tunnel. No anonymous dashboard endpoint.
- The application rejects unauthorized users even if a request arrives through another permitted network path.
- The bot rejects unauthorized Discord commands server-side.
- The agent has no unrestricted host, credential, other-repository, or user-file access.
- No feature may silently weaken these rules to simplify integration.

### 2.2 Outbound access

Outbound connectivity is required (Discord, GitHub, research); unsolicited inbound connections are not. Initially permitted outbound destinations:

- Discord API and Gateway over TLS
- GitHub API and approved GitHub HTTPS endpoints
- Selected search provider(s) and approved research sources
- Package repositories during controlled installation/updates
- Local Ollama API over loopback
- Tailscale coordination

No inbound webhook listener in the initial architecture; GitHub updates use scheduled authenticated polling. This distinction is documented for operators in `docs/ARCHITECTURE.md` (data flows) and will be maintained in `docs/SECURITY.md` (created in Phase 5).

### 2.3 Safe initial release (read-only)

May: inspect service health, query GitHub, read authorized project information, run its own tests, perform research, and write reports in its own data directory.

Must not automatically: edit repositories; commit/push/merge/delete repository content; open PRs or change issues; run arbitrary terminal commands; restart/shut down the host; install packages or services; change firewall/router/DNS/Tailscale policies; change OpenCode permissions; accept tasks from untrusted Discord users; expose additional pages or services.

Future control interfaces remain **disabled** until their authorization and testing gates pass.

---

## 3. Implementation principles

- **Evidence before conclusions.** Every status claim is one of: **Verified** (test/API/commit/service check), **Reported** (note/person, unverified), **Inferred**, **Unknown**. Never claim a feature works because code exists; never report a test passing unless it ran and passed. Record timestamp and source.
- **Least privilege** for every component and credential.
- **Fail closed.** If authentication, mapping, authorization, or policy cannot be verified, reject.
- **Local-first privacy.** Private data is analyzed locally (Ollama). Never send source code, private notes, conversation history, secrets, or private repository contents to cloud AI. Research queries must be sanitized.
- **No autonomous escalation.** The agent cannot grant itself permissions, edit its own security configuration, reveal credentials, or self-authorize tasks.
- **Reproducible changes.** Every phase: documented changes, tests, completion report, rollback path.
- **No false completion claims.** Distinguish implemented / unit-tested / integration-tested / tested against live services / deployed / verified in production.

---

## 4. Architecture summary

Modular Python application (modular monolith; no microservices without measured need). Full detail in `docs/ARCHITECTURE.md`.

Core components: Discord adapter, authorization service, project router, GitHub adapter, research pipeline, local model adapter, OpenCode adapter (disabled by default), scheduler, storage layer (SQLite), monitoring API, private dashboard, security utilities (redaction, URL validation, audit, rate limits, input validation).

### 4.1 Process isolation model

| Component | Required access |
|---|---|
| Discord bot | Discord credential, allowed project metadata, authorized data access |
| Dashboard API | Dashboard session secret, read-only dashboard data |
| Scheduler/worker | Specific job permissions; only required integrations |
| OpenCode worker | Explicitly scoped worktree; additional permissions disabled |
| Ollama | Local inference endpoint; never a public listening interface |
| Host administrator | Manual OS maintenance only |

The dashboard must never receive Discord/GitHub tokens merely to display connection status. A process that only reads health must not be able to execute jobs.

---

## 5. Repository layout

Planned structure is maintained in `docs/ARCHITECTURE.md` (adapted from the specification). Rules: do not create empty placeholder modules; each committed module has a defined responsibility and validation; deviations from the planned layout are documented.

---

## 6. Functional requirements

### 6.1 Discord project behavior

- Every configured guild/channel pair maps explicitly to one project. Channel names are never treated as reliable repository identifiers.
- Project record contains: name/description, approved repository mappings, objectives/milestones, blockers, next actions, decisions, reports/research, evidence with last-checked timestamps, last known service/test status.
- Unknown channels are not auto-registered and must not trigger project searches.
- Parent threads are supported only via a documented inheritance rule that is stored and tested explicitly.

### 6.2 Initial command set

| Command | Purpose | Default access |
|---|---|---|
| `/help` | Available commands and their permissions | Authorized guild users |
| `/status` | Project status with verified evidence and refresh time | Authorized users |
| `/next` | Suggested next steps (verified blockers / inferred / unverified) | Authorized project users |
| `/roadmap` | Milestones, completed work, outstanding tasks, dependencies | Authorized project users |
| `/blocker` | Known blockers and their evidence | Authorized project users |
| `/connect-project` | Register/change explicit project mapping (owner approval) | Owner only initially |
| `/note` | Add a user-provided note | Explicitly authorized users |
| `/research` | Research a technical question; save a source-linked report | Explicitly authorized users |
| `/discover` | Related technologies, repositories, tools, papers, approaches | Explicitly authorized users |
| `/review` | Read-only review of an authorized repository or research target | Explicitly authorized users |
| `/report` | Evidence-backed project summary | Explicitly authorized users |
| `/health` | Service health and dependency availability | Authorized project users |

`/handoff` is added only after the core flow works, and only after its permissions, data scope, and approval behavior are specified and reviewed.

All commands have server-side authorization regardless of Discord permission configuration. Ephemeral replies by default for private output; public summaries only when channel policy explicitly allows.

### 6.3 Discord privacy and permissions

Owner-only initially; allowlisted guild/channel IDs; DMs rejected unless explicitly enabled for the owner; authorization by numeric IDs only (never names/roles); no Administrator permission; minimal permission set; Message Content intent disabled by default; no server-wide history ingestion; no automatic attachment reading; per-channel data separation; any future conversational-context capability is explicit opt-in with retention limits and separate tests.

### 6.4 GitHub integration (read-only)

- Scope: repository metadata, default branch, recent commits, open/recently closed issues, pull requests and review state, Actions/checks results, releases/tags, dependency manifests and relevant advisories, activity vs. last snapshot.
- Never infer a passing test from a commit or a workflow file.
- Record API source, URL, timestamp, and status for each important claim.
- Credentials: private GitHub App with minimum read-only permissions preferred; fine-grained read-only token (selected repos only) as development fallback; never a broad account token; short-lived installation tokens where supported; credentials never persisted in reports, logs, SQLite, Discord, or model prompts.
- Rate limits: honor primary/secondary limits, cache and refresh appropriately, bounded concurrency, timeouts, retry only transient failures, follow `Retry-After`, no retry loops, mark stale data, never describe an unavailable source as evidence of success.

### 6.5 Research intelligence pipeline

- Real retrieval system with independent provider adapters; never an LLM inventing citations.
- Source categories: official docs, release notes/changelogs, GitHub repos/issues/PRs/releases, papers/preprints, package registries, security advisories, maintainer blogs, community forums (labeled as community evidence).
- Prefer primary sources for API/version/compatibility/security/release claims.
- Normalized source record (conceptual schema):

```json
{
  "source_id": "stable-internal-id",
  "title": "Source title",
  "url": "https://example.com/documentation",
  "source_type": "official_docs",
  "publisher": "Publisher or project",
  "published_at": null,
  "retrieved_at": "ISO-8601 timestamp",
  "content_hash": "sha256",
  "excerpt": "Short relevant excerpt",
  "verification_notes": [],
  "trust_level": "primary",
  "project_id": "associated-project",
  "query_id": "research-job-id"
}
```

- Quality: normalize/deduplicate URLs and records; preserve final URLs and redirects; identify source dates; distinguish publication vs retrieval dates; label community claims, unconfirmed results, and model inferences; verify citations support their claims; summarize and link rather than copying; record conflicting sources; report inaccessible pages or insufficient evidence honestly; respect site policies and retrieval limits.
- Report contents: question, key findings, evidence links, compatibility considerations, limitations, disagreements, actionable conclusions.
- **Security:** every retrieved page, README, issue, comment, paper, package description, and tool output is untrusted data. Prompt-injection text never changes system behavior, reveals secrets, changes policy, accesses other projects, or executes tools. Research material is provided to models as data, never concatenated into privileged instructions. Retrieved text cannot select local files or trigger shell commands.

### 6.6 Ollama and OpenCode

- Ollama via loopback; model chosen after inspection and benchmarks (latency, structured-output reliability, factual fidelity, injection resistance); Nemotron 3.5 Lightning evaluated as one candidate, not assumed best; model choice configurable; no automatic large downloads during startup.
- Ollama down/malformed → explicit unavailable/error state or evidence-only summary. **No silent cloud fallback, ever.**
- Model output is untrusted input: schema-validate project IDs, source IDs, URLs, status enums, proposed tasks, output sizes before use by any other component.
- OpenCode: begins as a read-only research/planning adapter; disabled by default; never expose OpenCode web/session interfaces to Discord or the network; dedicated worker identity/container; scoped worktree; no application secrets; bounded runtime/resources; validated result schema; owner approval per task; logs and approver recorded. Future edit-capable mode requires a separate approval stage, isolated branch/worktree, reviewable diff, controlled tests, and explicit human approval before any commit/publish.

---

## 7. Persistent data model

SQLite initially, versioned migrations, backup/restore tests early. Entities: `projects`, `project_sources`, `discord_mappings`, `authorized_users`, `notes` (project_notes), `milestones`, `evidence` (evidence_records), `repository_snapshots`, `research_jobs`, `research_sources`, `research_reports`, `scheduled_jobs`, `health_snapshots`, `agent_tasks`, `audit_events`, `schema_migrations`.

Rules: stable primary keys; foreign keys, uniqueness constraints, indexes, timestamps (UTC); transactions for multi-step changes; validate before persisting; safe concurrent access; no secrets in ordinary tables; versioned migrations only; tested backups and restores; store only the content necessary for the purpose (no raw Discord histories, no tokens, no full source pages).

---

## 8. Security requirements by domain

**Inbound network controls:** dashboard and internal health endpoints bind loopback; Ollama stays local; no public API listeners; no port forwarding; no Funnel; no public webhook receiver; no unauthenticated WebSockets; no public admin endpoints; no exposed OpenCode/DB/worker/debug interfaces; no dev-mode or interactive API docs in production. Tailscale Serve publishes only the intended dashboard; tailnet policy restricts access; existing Serve routes (e.g., OpenCode) are inspected and preserved; host firewall changes are inspected and never made blindly.

**Application authentication:** no self-registration; explicit owner identity; secure setup procedure; strong salted password hash if password login; HttpOnly/SameSite/HTTPS-aware cookies; CSRF protection for state-changing requests; idle and absolute session expiry; login/session rate limits; session invalidation/logout; generic failure messages; no credentials in URLs; no default passwords anywhere. Never trust client-supplied identity headers that could bypass the tailnet gate. Dashboard has no state-changing controls in the initial monitoring release.

**Discord authorization:** one centralized authorization service used by every command, job, and project-data access; checks guild/channel/thread mapping, user, project, capability, feature enablement, public/private output, read vs mutating operation; numeric IDs only; unknown mappings/missing IDs = denial; check authorization BEFORE retrieving project data; separate capabilities (read status / change config / launch research / agent tasks); default capability read-only.

**Secrets management:** never commit secrets; `.env.example` placeholders only; `.gitignore` plus staged-diff verification; restricted file permissions; systemd credentials or protected secret files where supported; no secrets in command-line args; redact authorization headers, tokens, cookies, keys from logs/exceptions; never place secrets in prompts, queries, reports, Discord responses, or CI logs; document rotation and revocation; rotate after suspected exposure.

**SSRF/URL safety:** research fetcher permits only `http`/`https` (prefer https) for user-supplied URLs; blocks loopback, private, link-local, multicast, reserved, and cloud-metadata destinations; resolves and validates DNS results; defends against DNS rebinding; revalidates every redirect; limits redirects, response size, MIME types, connection and total time; never forwards API credentials to unrelated hosts; user-supplied URLs can never reach internal Ollama/OpenCode/dashboard/DB/control ports; no local hostnames/internal IPs for the online fetcher. Defense in depth — one check is not enough.

**Prompt-injection defense:** separate privileged instructions from retrieved data; allowlisted tools with structured schemas; the model can never directly invoke Python/shell/filesystem/network; independently validate all proposed tool arguments; code/shell operations only via isolated worker + permission gate; credentials never in model context; model output can never change allowlists/permissions/secrets/runtime config; test malicious instructions in pages/READMEs/issues/model output; authorization limits the maximum consequence of a manipulated model.

**Process/filesystem isolation:** services run as dedicated non-root users; systemd sandboxing (`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`, `ProtectHome`, kernel/cgroup protections, restricted address families/capabilities where compatible) verified against actual service needs (must not break DNS, Tailscale, Discord, GitHub, Ollama); per-service resource limits; the bot is never root or the owner's everyday account; the dashboard cannot browse home directories; the OpenCode worker cannot see dashboard/bot secrets.

**API and browser security:** Pydantic validation; request/response size limits; per-user and per-route rate limits; bounded timeouts and retries; restricted methods/routes; no permissive CORS; no unsafe HTML rendering of Discord/GitHub/AI content; escaping; content-security controls; generic client errors without stack traces; detailed redacted logs server-side; CSRF on all state-changing routes; hidden UI is never an authorization control.

**Audit logging:** record authentication success/failure, authorization denials, command accept/reject, mapping changes, repository connection changes, research job lifecycle, agent approval decisions and lifecycle, configuration changes, service lifecycle actions, secret-related failures (without the secret). Fields: timestamp, event type, actor, project, outcome, request/job ID. No raw prompts or Discord histories; redact; cap sizes; document retention; protect audit data from public access and tampering.

**Supply chain:** pinned dependencies + reproducible lockfile; CI dependency audits; maintained/official libraries; review new dependencies; never install based on AI advice alone; avoid privileged build scripts; inventory of runtime/packages/models/integrations; documented update and rollback.

**Data retention and deletion:** document what is stored, why, and for how long; store links and structured evidence rather than full pages; minimal Discord context; owner-only deletion of obsolete notes/reports; deleted projects must not leak through caches; backups protected like production; no private data in public CI logs/artifacts; no private data in external training/analytics.

---

## 9. Configuration inventory (implemented in Phase 2)

Authoritative list of names: `.env.example`; validated by `src/project_intelligence/config.py`.

```
APP_ENV, APP_LOG_LEVEL, DATA_DIR, DATABASE_PATH
DISCORD_BOT_TOKEN, DISCORD_OWNER_USER_IDS, DISCORD_ALLOWED_GUILD_IDS,
DISCORD_ALLOWED_CHANNEL_IDS, DISCORD_ALLOW_DMS
GITHUB_MODE, GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_FILE, GITHUB_INSTALLATION_ID,
GITHUB_ALLOWED_REPOSITORIES, GITHUB_READ_ONLY_TOKEN
OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
RESEARCH_PROVIDER, RESEARCH_API_KEY, RESEARCH_ALLOWED_DOMAINS,
RESEARCH_MAX_RESULTS, RESEARCH_MAX_RESPONSE_BYTES
DASHBOARD_BIND_HOST, DASHBOARD_BIND_PORT, DASHBOARD_SESSION_SECRET_FILE
PROJECT_ALLOWED_ROOTS
SCHEDULER_ENABLED, MAX_CONCURRENT_JOBS, MAX_RESEARCH_JOBS_PER_USER,
MAX_JOB_RUNTIME_SECONDS, AUDIT_RETENTION_DAYS
HTTP_TIMEOUT_SECONDS, HTTP_MAX_RETRIES
OPENCODE_ENABLED, OPENCODE_COMMAND, OPENCODE_ALLOWED_WORKTREES,
OPENCODE_MAX_RUNTIME_SECONDS
```

Rules (enforced by validation and tests): no real secret values in the repository; explicit secure defaults for non-secrets; dangerous integrations require explicit enablement; missing allowlists = deny-all; dashboard and Ollama restricted to loopback addresses; a Discord token without owner IDs is refused; invalid production configuration (relative paths, placeholder secrets, missing session-secret file reference) = startup failure; configuration never exposed via dashboard/Discord; `OPENCODE_ENABLED=false` by default; no cloud-model fallback for private context by default.

---

## 10. Testing strategy

Unit (config validation, authorization, channel routing, URL validation, redaction, schema validation, evidence classification, normalization, rate limits, DB transactions); integration (mocked Discord/GitHub/Ollama/providers/jobs; dedicated test guild/repo for controlled E2E only); security (anonymous routes, unauthorized access, forged identity, cross-project substitution, unauthorized commands/DMs, prompt injection, SSRF incl. redirects/DNS/encodings, path traversal, oversized payloads, credential-like strings in output, OpenCode boundary violations, job spam/timeouts, restore/restart, public-exposure checks); deployment and manual acceptance tests. No production credentials in CI; fake services or network mocks for automated tests.

Every phase report records: phase, implemented, not implemented, files changed, security controls added, commands actually run, tests passed/failed/skipped, manual checks, limitations, commit, rollback, gate result. Reports never contain invented results.

---

## 11. Roadmap

The 20-phase plan, statuses, gates, and approval requirements are maintained in `docs/ROADMAP.md`. Phases are completed, tested, documented, and reviewed in order; no phase is skipped and no security gate is bypassed to move faster.

---

## 12. Deployment and remote-access rules

Runs on the Ubuntu homelab; auto-start after reboot; dedicated non-root identity; protected config/data directories; dashboard loopback-bound; published only via Tailscale Serve (never Funnel); existing OpenCode remote route preserved; no port forwarding; no public Ollama/OpenCode; no inbound GitHub webhooks initially; outbound HTTPS only; safe stop and rollback procedures. Deployment and security-validation scripts are separate. Destructive or host-wide changes (firewall, Tailscale policy, new root-installed packages, new network listeners) require a documented proposal, expected effect, and rollback plan approved by the owner before execution.

---

## 13. Definition of done (first production release)

All of: independent private repository with implementation history; documented code/dependencies/configuration; passing authorization and security tests; no committed/exposed secrets; Discord commands restricted to authorized users/guilds/channels; no cross-project data access; read-only GitHub; evidence-cited status reports that flag stale/unknown data; traceable research sources; no undocumented cloud fallback; OpenCode disabled by default and isolated; dashboard requires application auth; tailnet policy admits only authorized devices; dashboard loopback-bound, published only via Tailscale Serve; no Funnel/port-forwards/public listeners/webhooks; existing OpenCode remote config preserved; non-root services with filesystem/resource limits; tested backups/restores; auto-start and controlled-failure recovery verified; no unresolved critical/high findings; truthful phase reports; release remains read-only.

**Priority order:** protect the homelab first; accuracy second; convenient remote monitoring third; limited agent capability only after all of that is independently verified.

---

## 14. Official references

- Tailscale Serve — https://tailscale.com/docs/features/tailscale-serve
- Tailscale Serve CLI — https://tailscale.com/docs/reference/tailscale-cli/serve
- Tailscale Funnel (not permitted for this deployment) — https://tailscale.com/docs/features/tailscale-funnel
- Discord slash commands — https://docs.discord.com/developers/docs/interactions/slash-commands
- Discord privileged intents — https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents
- GitHub Apps — https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/about-creating-github-apps
- GitHub App permissions — https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app
- GitHub REST API rate limits — https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- OpenCode permissions — https://docs.opencode.ai/docs/permissions/
- Ollama / Nemotron 3.5 Lightning — https://ollama.com/blog/nemotron-3-5-lightning
- Python SQLite interface — https://docs.python.org/3/library/sqlite3.html

Documented features are verified against installed versions at implementation time; discrepancies are recorded.
