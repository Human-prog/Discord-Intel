"""Image vision (Phase 26+).

Analyzes images via Ollama vision models (llava, etc.).
Degrades safely when Ollama or vision model unavailable.
"""

from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)


class VisionEngine:
    """Analyze images using Ollama vision models."""

    def __init__(self, model: str = "llava:7b") -> None:
        self.model = model
        self._available = False

    def _check(self) -> bool:
        if self._available:
            return True
        try:
            from project_intelligence.config import load_settings

            settings = load_settings()
            self._base_url = settings.ollama_base_url
            self._timeout = settings.ollama_timeout_second
            import httpx

            self._httpx = httpx
            self._available = True
            logger.info("Vision engine ready (model: %s)", self.model)
        except Exception as exc:
            logger.warning("Vision engine unavailable: %s", exc)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._check()

    def analyze(self, image_path: str, prompt: str = "Describe this image in detail") -> str | None:
        """Send an image to Ollama vision model and return the analysis."""
        if not self._check():
            return None
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [b64],
                "stream": False,
            }
            resp = self._httpx.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip() or None
        except Exception as exc:
            logger.warning("Vision analysis failed: %s", exc)
            return None

    def describe(self, image_path: str) -> str | None:
        return self.analyze(image_path, "Describe this image in detail")


# Global instance (lazy init)
_vision: VisionEngine | None = None


def get_vision_engine() -> VisionEngine:
    global _vision
    if _vision is None:
        _vision = VisionEngine()
    return _vision
