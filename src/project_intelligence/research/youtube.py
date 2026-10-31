"""YouTube video content extraction for research pipeline.

Fetches video metadata and transcript/caption text from YouTube URLs.
All content is treated as untrusted data and cited like web sources.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from project_intelligence.config import Settings, load_settings
from project_intelligence.research.research_pipeline import is_safe_url
from project_intelligence.research.web_research import (
    ResearchError,
    WebFinding,
)

# YouTube URL patterns
YOUTUBE_URL_PATTERNS = [
    re.compile(r"^https?://(?:www\.)?youtube\.com/watch\?v=([^&]+)"),
    re.compile(r"^https?://youtu\.be/([^?&]+)"),
    re.compile(r"^https?://(?:www\.)?youtube\.com/shorts/([^?&]+)"),
    re.compile(r"^https?://(?:www\.)?youtube\.com/embed/([^?&]+)"),
]


@dataclass
class YouTubeVideo:
    """Parsed YouTube video metadata and transcript."""

    video_id: str
    url: str
    title: str
    description: str
    duration_seconds: int | None
    view_count: int | None
    published_at: str | None
    transcript_text: str | None
    transcript_language: str | None
    fetched_at_utc: str
    content_hash: str


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    for pattern in YOUTUBE_URL_PATTERNS:
        match = pattern.match(url)
        if match:
            return match.group(1)
    return None


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL."""
    return extract_video_id(url) is not None


class YouTubeFetcher:
    """Fetch YouTube video metadata and transcript using public endpoints.

    Uses YouTube's oEmbed endpoint for metadata and timedtext API for captions.
    No API key required for public videos.
    """

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or load_settings()
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": "DiscordProjectIntelligence/0.1 (+private research)",
                    "Accept": "application/json, text/xml, */*",
                },
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _validate_youtube_url(self, url: str) -> str:
        """Validate URL is a safe, public YouTube video URL."""
        if not is_safe_url(url):
            raise ResearchError("Refusing to fetch an unsafe or non-public URL")
        if not is_youtube_url(url):
            raise ResearchError("URL is not a recognized YouTube video URL")
        return url

    def fetch_video(self, url: str) -> YouTubeVideo:
        """Fetch video metadata and transcript from a YouTube URL."""
        url = self._validate_youtube_url(url)
        video_id = extract_video_id(url)
        if not video_id:
            raise ResearchError("Could not extract video ID from URL")

        # Fetch metadata via oEmbed
        title, description, duration_seconds, view_count, published_at = self._fetch_metadata(video_id)

        # Fetch transcript
        transcript_text, transcript_language = self._fetch_transcript(video_id)

        # Build content hash
        content_for_hash = f"{title}|{description}|{transcript_text or ''}"
        import hashlib
        content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()

        return YouTubeVideo(
            video_id=video_id,
            url=url,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            view_count=view_count,
            published_at=published_at,
            transcript_text=transcript_text,
            transcript_language=transcript_language,
            fetched_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            content_hash=content_hash,
        )

    def _fetch_metadata(self, video_id: str) -> tuple[str, str, int | None, int | None, str | None]:
        """Fetch video metadata via YouTube oEmbed."""
        oembed_url = "https://www.youtube.com/oembed"
        params = {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}

        try:
            response = self._http().get(oembed_url, params=params)
            if response.status_code == 404:
                raise ResearchError("Video not found or private")
            response.raise_for_status()
            data = response.json()
            title = str(data.get("title", f"YouTube video {video_id}"))[:300]
            description = str(data.get("author_name", ""))[:500]
            # oEmbed doesn't provide duration, views, or publish date
            # We'll fetch those from the video page
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchError(f"Could not fetch video metadata: {type(exc).__name__}") from None

        # Fetch video page for additional metadata
        try:
            page_response = self._http().get(f"https://www.youtube.com/watch?v={video_id}")
            page_response.raise_for_status()
            html = page_response.text

            # Extract metadata from ytInitialData JSON embedded in page
            import json
            match = re.search(r"var ytInitialData = ({.*?});", html)
            if match:
                try:
                    yt_data = json.loads(match.group(1))
                    # Navigate to video details - structure varies
                    # This is best-effort; if parsing fails we fall back to oEmbed title
                    video_details = self._extract_video_details(yt_data)
                    if video_details:
                        duration_seconds = video_details.get("duration_seconds")
                        view_count = video_details.get("view_count")
                        published_at = video_details.get("published_at")
                        if not description:
                            description = video_details.get("description", "")
                    else:
                        duration_seconds = view_count = published_at = None
                except (json.JSONDecodeError, KeyError, TypeError):
                    duration_seconds = view_count = published_at = None
            else:
                duration_seconds = view_count = published_at = None
        except (httpx.HTTPError, ValueError):
            duration_seconds = view_count = published_at = None

        return title, description, duration_seconds, view_count, published_at

    def _extract_video_details(self, yt_data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract video details from ytInitialData. Best-effort due to changing structure."""
        try:
            # Navigate through the complex nested structure
            contents = yt_data.get("contents", {})
            two_column = contents.get("twoColumnWatchNextResults", {})
            results = two_column.get("results", {})
            results_contents = results.get("results", {}).get("contents", [])

            for item in results_contents:
                video_primary = item.get("videoPrimaryInfoRenderer", {})
                if video_primary:
                    # Extract duration
                    duration_seconds = None
                    duration_label = video_primary.get("videoDuration", {})
                    if isinstance(duration_label, dict):
                        duration_text = duration_label.get("simpleText", "")
                        duration_seconds = self._parse_duration(duration_text)

                    # Extract view count
                    view_count = None
                    view_count_renderer = video_primary.get("viewCount", {})
                    if isinstance(view_count_renderer, dict):
                        view_count_text = view_count_renderer.get("simpleText", "")
                        view_count = self._parse_view_count(view_count_text)

                    # Extract description
                    description = ""
                    description_rows = video_primary.get("description", {}).get("runs", [])
                    for run in description_rows:
                        if isinstance(run, dict) and "text" in run:
                            description += run["text"]

                    return {
                        "duration_seconds": duration_seconds,
                        "view_count": view_count,
                        "published_at": None,  # Not easily accessible in this structure
                        "description": description,
                    }
        except Exception:  # noqa: S110
            pass
        return None

    def _parse_duration(self, duration_text: str) -> int | None:
        """Parse duration string like '1:23:45' or '12:34' to seconds."""
        try:
            parts = [int(p) for p in duration_text.split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
        except ValueError:
            pass
        return None

    def _parse_view_count(self, view_text: str) -> int | None:
        """Parse view count string like '1.2M views' or '1,234 views'."""
        try:
            text = view_text.lower().replace("views", "").replace("view", "").strip()
            text = text.replace(",", "")
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            if "m" in text:
                return int(float(text.replace("m", "")) * 1000000)
            return int(text)
        except ValueError:
            return None

    def _fetch_transcript(self, video_id: str) -> tuple[str | None, str | None]:
        """Fetch transcript/caption text from YouTube's timedtext API."""
        # First, get the caption tracks list
        timedtext_url = "https://www.youtube.com/api/timedtext"
        params = {"v": video_id, "format": "3gp", "xorb": "1", "xobt": "2"}

        try:
            response = self._http().get(timedtext_url, params=params)
            if response.status_code == 404:
                return None, None
            response.raise_for_status()

            # Parse XML transcript
            xml_content = response.text
            if not xml_content.strip():
                return None, None

            root = ET.fromstring(xml_content)  # noqa: S314
            transcript_parts = []
            lang_code = root.get("lang_code", "en")

            for text_elem in root.findall(".//text"):
                if text_elem.text:
                    transcript_parts.append(text_elem.text)

            transcript = " ".join(transcript_parts).strip()
            if not transcript:
                return None, None

            # Truncate to reasonable size
            transcript = transcript[:20000]
            return transcript, lang_code

        except (httpx.HTTPError, ET.ParseError, ValueError):
            return None, None


def youtube_to_web_finding(video: YouTubeVideo) -> WebFinding:
    """Convert a YouTubeVideo to a WebFinding for unified research reporting."""
    content_parts = []
    if video.description:
        content_parts.append(f"Description: {video.description[:1000]}")
    if video.transcript_text:
        content_parts.append(f"Transcript: {video.transcript_text[:2000]}")

    content = "\n\n".join(content_parts)
    snippet = video.transcript_text[:600] if video.transcript_text else video.description[:600]

    return WebFinding(
        title=video.title,
        url=video.url,
        snippet=snippet,
        score=1.0,
        provider="youtube",
        content=content,
        content_hash=video.content_hash,
        fetched_at_utc=video.fetched_at_utc,
        metadata={
            "video_id": video.video_id,
            "duration_seconds": video.duration_seconds,
            "view_count": video.view_count,
            "published_at": video.published_at,
            "transcript_language": video.transcript_language,
            "has_transcript": video.transcript_text is not None,
        },
    )


def research_youtube(
    question: str,
    urls: list[str],
    *,
    settings: Settings | None = None,
    fetcher: YouTubeFetcher | None = None,
) -> tuple[list[WebFinding], str]:
    """Research specific YouTube URLs and build a cited report.

    Args:
        question: The research question (for report header)
        urls: List of YouTube video URLs to analyze
        settings: Optional Settings override
        fetcher: Optional YouTubeFetcher for testing

    Returns:
        Tuple of (list of WebFinding, markdown report string)
    """
    settings = settings or load_settings()
    owns_fetcher = fetcher is None
    fetcher = fetcher or YouTubeFetcher(settings)

    findings: list[WebFinding] = []
    try:
        for url in urls:
            try:
                video = fetcher.fetch_video(url)
                finding = youtube_to_web_finding(video)
                findings.append(finding)
            except ResearchError:
                # Keep going - log but don't fail the whole batch
                continue

        # Build report
        lines = [
            "# YouTube research",
            "",
            f"**Question:** {question}",
            "**Source type:** YouTube videos",
            f"**Videos analyzed:** {len(findings)}",
            "",
        ]

        if not findings:
            lines.append("No valid YouTube videos could be analyzed.")
            return findings, "\n".join(lines)

        for index, finding in enumerate(findings, start=1):
            lines.append(f"### [{index}] {finding.title}")
            lines.append(f"<{finding.url}>")
            lines.append("")
            if finding.snippet:
                lines.append(f"> {finding.snippet.strip()}")
                lines.append("")
            if finding.content:
                excerpt = finding.content[:1500].strip()
                lines.append(excerpt + ("…" if len(finding.content) > 1500 else ""))
                lines.append("")
            meta = ["source: youtube"]
            if finding.fetched_at_utc:
                meta.append(f"fetched: {finding.fetched_at_utc}")
            if finding.content_hash:
                meta.append(f"sha256: {finding.content_hash[:16]}…")
            if finding.metadata.get("duration_seconds"):
                mins = finding.metadata["duration_seconds"] // 60
                secs = finding.metadata["duration_seconds"] % 60
                meta.append(f"duration: {mins}:{secs:02d}")
            if finding.metadata.get("view_count"):
                meta.append(f"views: {finding.metadata['view_count']:,}")
            if finding.metadata.get("transcript_language"):
                meta.append(f"transcript: {finding.metadata['transcript_language']}")
            lines.append(f"*{' · '.join(meta)}*")
            lines.append("")

        return findings, "\n".join(lines).rstrip() + "\n"

    finally:
        if owns_fetcher:
            fetcher.close()
