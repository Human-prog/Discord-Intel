"""Local research over the project catalog and recorded work.

The local researcher answers a question from data we already own: imported
projects, Git work items, notes, milestones, evidence, and earlier research
reports.  It deliberately uses transparent keyword scoring rather than a
remote model, so it works offline and every result carries a stable citation
reference (``project:3``, ``note:12``, ``work:44``...).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from project_intelligence.config import Settings, load_settings
from project_intelligence.storage.database import get_conn

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.#-]*")
_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "me",
        "more",
        "most",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "out",
        "over",
        "should",
        "so",
        "some",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "up",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "work",
        "worked",
        "working",
        "would",
        "you",
    }
)

_FIELD_WEIGHTS = {
    "project_name": 6.0,
    "project_description": 2.5,
    "project_meta": 1.5,
    "work_title": 4.0,
    "work_body": 1.5,
    "note": 3.0,
    "milestone": 2.5,
    "evidence": 2.0,
    "report": 1.0,
}


def tokenize(text: str) -> list[str]:
    """Return stable, lowercase search tokens without common stopwords."""
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_RE.findall(text.lower()):
        token = raw.strip("._-")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token.endswith("s") and len(token) > 4 and token.isalpha():
            token = token[:-1]
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _parse_metadata(value: object) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_list(value: object) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


@dataclass
class LocalFinding:
    """One locally-owned record that matches the research question."""

    source_type: str
    source_ref: str
    title: str
    snippet: str
    score: float
    project_id: int | None = None
    project_name: str | None = None
    occurred_at_utc: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def _score_tokens(tokens: list[str], text: str, weight: float, phrase: str) -> tuple[float, int]:
    """Return ``(score, matched_token_count)`` for one field."""
    if not tokens:
        return 0.0, 0
    lowered = text.lower()
    matched = sum(1 for token in tokens if token in lowered)
    if matched == 0:
        return 0.0, 0
    score = weight * matched
    # Matching the whole question is a strong signal, not a replacement for
    # token coverage.
    if len(tokens) > 1 and phrase and phrase in lowered:
        score += weight
    return score, matched


def _snippet(text: str, limit: int = 320) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


class LocalResearcher:
    """Keyword researcher over the application's own SQLite records."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.conn = get_conn()

    def search(
        self,
        question: str,
        *,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[LocalFinding]:
        tokens = tokenize(question)
        if not tokens:
            return []
        phrase = " ".join(question.lower().split())
        max_results = limit or max(10, self.settings.research_max_results * 2)

        findings: list[LocalFinding] = []
        findings.extend(self._search_projects(tokens, phrase, project_id))
        findings.extend(self._search_work_items(tokens, phrase, project_id))
        findings.extend(self._search_notes(tokens, phrase, project_id))
        findings.extend(self._search_milestones(tokens, phrase, project_id))
        findings.extend(self._search_evidence(tokens, phrase, project_id))
        findings.extend(self._search_reports(tokens, phrase, project_id))

        findings.sort(key=lambda item: (-item.score, item.source_type, item.source_ref))
        return findings[: max(1, min(max_results, 100))]

    # ------------------------------------------------------------------
    # Per-table searches.  Each returns findings with a stable citation.
    # ------------------------------------------------------------------

    def _project_rows(self, project_id: int | None) -> list[sqlite3.Row]:
        sql = (
            "SELECT id, name, description, allowed_root, catalog_status, category, "
            "priority, tech_stack_json, repo_url, last_activity_utc, metadata_json "
            "FROM projects"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE id = ?"
            params = (project_id,)
        sql += " ORDER BY name"
        return self.conn.execute(sql, params).fetchall()

    def _project_names(self) -> dict[int, str]:
        rows = self.conn.execute("SELECT id, name FROM projects").fetchall()
        return {int(row[0]): str(row[1]) for row in rows}

    def _search_projects(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        names = self._project_names()
        results: list[LocalFinding] = []
        for row in self._project_rows(project_id):
            pid = int(row[0])
            name = _text(row[1])
            description = _text(row[2])
            metadata = _parse_metadata(row[10])
            tech = ", ".join(_parse_list(row[7]))
            extra = " ".join(
                part
                for part in (
                    _text(row[5]),
                    _text(row[6]),
                    tech,
                    _text(row[8]),
                    _text(row[4]),
                )
                if part
            )
            name_score, name_matches = _score_tokens(
                tokens, name, _FIELD_WEIGHTS["project_name"], phrase
            )
            desc_score, desc_matches = _score_tokens(
                tokens, description, _FIELD_WEIGHTS["project_description"], phrase
            )
            extra_score, extra_matches = _score_tokens(
                tokens, extra, _FIELD_WEIGHTS["project_meta"], phrase
            )
            score = name_score + desc_score + extra_score
            if score <= 0:
                continue
            snippet_parts = [description] if description else []
            if tech:
                snippet_parts.append(f"Tech: {tech}")
            if row[4]:
                snippet_parts.append(f"Status: {_text(row[4])}")
            results.append(
                LocalFinding(
                    source_type="project",
                    source_ref=f"project:{pid}",
                    title=f"Project: {name}",
                    snippet=_snippet(" · ".join(snippet_parts) or name),
                    score=score,
                    project_id=pid,
                    project_name=names.get(pid, name),
                    occurred_at_utc=_text(row[9]) or None,
                    metadata={
                        "matched_terms": name_matches + desc_matches + extra_matches,
                        "metadata": metadata,
                    },
                )
            )
        return results

    def _search_work_items(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        sql = (
            "SELECT w.id, w.project_id, w.work_type, w.title, w.body, w.source, "
            "w.external_id, w.occurred_at_utc, p.name "
            "FROM work_items w LEFT JOIN projects p ON p.id = w.project_id"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE w.project_id = ?"
            params = (project_id,)
        sql += " ORDER BY COALESCE(w.occurred_at_utc, w.created_at_utc) DESC LIMIT 5000"
        results: list[LocalFinding] = []
        for row in self.conn.execute(sql, params).fetchall():
            title = _text(row[3])
            body = _text(row[4])
            title_score, title_matches = _score_tokens(
                tokens, title, _FIELD_WEIGHTS["work_title"], phrase
            )
            body_score, body_matches = _score_tokens(
                tokens, body, _FIELD_WEIGHTS["work_body"], phrase
            )
            score = title_score + body_score
            if score <= 0:
                continue
            results.append(
                LocalFinding(
                    source_type="work",
                    source_ref=f"work:{int(row[0])}",
                    title=f"{_text(row[2]).title()}: {title}",
                    snippet=_snippet(body or title),
                    score=score,
                    project_id=int(row[1]),
                    project_name=_text(row[8]) or None,
                    occurred_at_utc=_text(row[7]) or None,
                    metadata={
                        "source": _text(row[5]),
                        "external_id": _text(row[6]),
                        "matched_terms": title_matches + body_matches,
                    },
                )
            )
        return results

    def _search_notes(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        sql = (
            "SELECT n.id, n.project_id, n.content, n.created_at_utc, p.name "
            "FROM notes n LEFT JOIN projects p ON p.id = n.project_id"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE n.project_id = ?"
            params = (project_id,)
        sql += " ORDER BY n.created_at_utc DESC LIMIT 5000"
        results: list[LocalFinding] = []
        for row in self.conn.execute(sql, params).fetchall():
            content = _text(row[2])
            score, matched = _score_tokens(tokens, content, _FIELD_WEIGHTS["note"], phrase)
            if score <= 0:
                continue
            results.append(
                LocalFinding(
                    source_type="note",
                    source_ref=f"note:{int(row[0])}",
                    title="Note",
                    snippet=_snippet(content),
                    score=score,
                    project_id=None if row[1] is None else int(row[1]),
                    project_name=_text(row[4]) or None,
                    occurred_at_utc=_text(row[3]) or None,
                    metadata={"matched_terms": matched},
                )
            )
        return results

    def _search_milestones(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        sql = (
            "SELECT m.id, m.project_id, m.title, m.description, m.status, "
            "m.target_date_utc, p.name FROM milestones m "
            "LEFT JOIN projects p ON p.id = m.project_id"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE m.project_id = ?"
            params = (project_id,)
        sql += " ORDER BY m.created_at_utc DESC LIMIT 5000"
        results: list[LocalFinding] = []
        for row in self.conn.execute(sql, params).fetchall():
            text = f"{_text(row[2])} {_text(row[3])}".strip()
            score, matched = _score_tokens(tokens, text, _FIELD_WEIGHTS["milestone"], phrase)
            if score <= 0:
                continue
            results.append(
                LocalFinding(
                    source_type="milestone",
                    source_ref=f"milestone:{int(row[0])}",
                    title=f"Milestone: {_text(row[2])}",
                    snippet=_snippet(f"{_text(row[3])} ({_text(row[4])})"),
                    score=score,
                    project_id=int(row[1]),
                    project_name=_text(row[6]) or None,
                    occurred_at_utc=_text(row[5]) or None,
                    metadata={"status": _text(row[4]), "matched_terms": matched},
                )
            )
        return results

    def _search_evidence(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        sql = (
            "SELECT e.id, e.project_id, e.title, e.claim, e.retrieved_at_utc, p.name "
            "FROM evidence e LEFT JOIN projects p ON p.id = e.project_id"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE e.project_id = ?"
            params = (project_id,)
        sql += " ORDER BY e.retrieved_at_utc DESC LIMIT 5000"
        results: list[LocalFinding] = []
        for row in self.conn.execute(sql, params).fetchall():
            text = f"{_text(row[2])} {_text(row[3])}".strip()
            score, matched = _score_tokens(tokens, text, _FIELD_WEIGHTS["evidence"], phrase)
            if score <= 0:
                continue
            results.append(
                LocalFinding(
                    source_type="evidence",
                    source_ref=f"evidence:{int(row[0])}",
                    title=f"Evidence: {_text(row[2])}",
                    snippet=_snippet(_text(row[3]) or _text(row[2])),
                    score=score,
                    project_id=None if row[1] is None else int(row[1]),
                    project_name=_text(row[5]) or None,
                    occurred_at_utc=_text(row[4]) or None,
                    metadata={"matched_terms": matched},
                )
            )
        return results

    def _search_reports(
        self, tokens: list[str], phrase: str, project_id: int | None
    ) -> list[LocalFinding]:
        sql = (
            "SELECT r.id, j.id, j.project_id, j.question, r.report_text, "
            "r.generated_at_utc, p.name FROM research_reports r "
            "JOIN research_jobs j ON j.id = r.research_job_id "
            "LEFT JOIN projects p ON p.id = j.project_id"
        )
        params: tuple[object, ...] = ()
        if project_id is not None:
            sql += " WHERE j.project_id = ?"
            params = (project_id,)
        sql += " ORDER BY r.generated_at_utc DESC LIMIT 500"
        results: list[LocalFinding] = []
        for row in self.conn.execute(sql, params).fetchall():
            text = f"{_text(row[3])} {_text(row[4])}".strip()
            score, matched = _score_tokens(tokens, text, _FIELD_WEIGHTS["report"], phrase)
            if score <= 0:
                continue
            results.append(
                LocalFinding(
                    source_type="report",
                    source_ref=f"research:{int(row[1])}",
                    title=f"Earlier research: {_text(row[3])[:90]}",
                    snippet=_snippet(_text(row[4])),
                    score=score,
                    project_id=None if row[2] is None else int(row[2]),
                    project_name=_text(row[6]) or None,
                    occurred_at_utc=_text(row[5]) or None,
                    metadata={"matched_terms": matched},
                )
            )
        return results


def build_local_report(question: str, findings: list[LocalFinding]) -> str:
    """Render local findings as a cited Markdown report."""
    lines = [
        "# Local research",
        "",
        f"**Question:** {question}",
        "",
    ]
    if not findings:
        lines.append("No matching local records were found.")
        return "\n".join(lines)

    lines.append(
        f"Found **{len(findings)}** relevant local record"
        f"{'' if len(findings) == 1 else 's'} across projects, work history, "
        "notes, milestones, evidence, and earlier research."
    )
    lines.append("")
    for index, finding in enumerate(findings, start=1):
        lines.append(f"### [{index}] {finding.title}")
        project = finding.project_name or "workspace"
        when = f" · {finding.occurred_at_utc}" if finding.occurred_at_utc else ""
        lines.append(f"*{project}{when} · `{finding.source_ref}` · score {finding.score:.2f}*")
        lines.append("")
        lines.append(finding.snippet or "(no text)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def research_local(
    question: str,
    *,
    project_id: int | None = None,
    settings: Settings | None = None,
    limit: int | None = None,
) -> tuple[list[LocalFinding], str]:
    """Convenience entry point returning findings and the Markdown report."""
    settings = settings or load_settings()
    researcher = LocalResearcher(settings)
    findings = researcher.search(question, project_id=project_id, limit=limit)
    return findings, build_local_report(question, findings)


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp used by research provenance."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
