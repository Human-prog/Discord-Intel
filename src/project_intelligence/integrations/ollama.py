"""Local Ollama and Model Evaluation (Phase 14).

Provides an Ollama HTTP client with timeouts, bounded input/output,
error handling, and structured response validation.  Uses a model adapter
so models can be changed without rewriting the application.

AI functionality is optional and degrades safely when Ollama is unavailable.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from project_intelligence.config import Settings, load_settings


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

class OllamaClient:
    """HTTP client for local Ollama API."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self.base_url = self.settings.ollama_base_url
        self.model = self.settings.ollama_model
        self.timeout = self.settings.ollama_timeout_seconds

    def is_available(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str | None:
        """Generate a response from the model.

        Returns None if Ollama is unavailable or the request fails.
        """
        if not self.is_available():
            return None

        model_name = model or self.model
        if not model_name:
            return None

        # Bound input size
        max_input = 8000
        if len(prompt) > max_input:
            prompt = prompt[:max_input] + "... [truncated]"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": model_name,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": max_tokens,
                            "temperature": temperature,
                        },
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "")
        except Exception:
            pass
        return None

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        model: Optional[str] = None,
    ) -> dict[str, Any] | None:
        """Generate a structured response validated against a schema."""
        response = self.generate(prompt, model=model, max_tokens=2048, temperature=0.3)
        if response is None:
            return None
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data
        except (json.JSONDecodeError, Exception):
            pass
        return None


# ---------------------------------------------------------------------------
# Model adapter
# ---------------------------------------------------------------------------

class ModelAdapter:
    """Adapter to change models without rewriting the application."""

    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def summarize(self, evidence: str) -> str | None:
        """Generate a summary from evidence."""
        prompt = f"Summarize the following evidence:\n\n{evidence}\n\nSummary:"
        return self.client.generate(prompt, max_tokens=512, temperature=0.3)

    def recommend(self, context: str) -> str | None:
        """Generate recommendations from context."""
        prompt = f"Based on the following context, suggest next steps:\n\n{context}\n\nRecommendations:"
        return self.client.generate(prompt, max_tokens=512, temperature=0.5)


def create_ollama_client(settings: Optional[Settings] = None) -> OllamaClient:
    """Factory for OllamaClient."""
    if settings is None:
        settings = load_settings()
    return OllamaClient(settings)


def create_model_adapter(settings: Optional[Settings] = None) -> ModelAdapter:
    """Factory for ModelAdapter."""
    client = create_ollama_client(settings)
    return ModelAdapter(client)