"""Image Generation (Phase 26+).

Local text-to-image via Stable Diffusion (diffusers) or remote via
configured providers. Degrades safely when packages/models missing.
Uses Torch (already installed) + diffusers pipeline.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images from text prompts."""

    def __init__(self, model_id: str = "runwayml/stable-diffusion-v1-5") -> None:
        self.model_id = model_id
        self._pipeline = None
        self._available = False

    def _load(self) -> bool:
        if self._pipeline is not None:
            return self._available
        try:
            import torch
            from diffusers import StableDiffusionPipeline  # type: ignore

            self._pipeline = StableDiffusionPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float32,
                safety_checker=None,
            )
            # Use CPU if CUDA unavailable (already running on server)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._pipeline = self._pipeline.to(device)
            self._available = True
            logger.info("Image generation loaded (model: %s, device: %s)", self.model_id, device)
        except Exception as exc:
            logger.info("Image generation unavailable (diffusers/model missing): %s", exc)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._load()

    def generate(self, prompt: str, output_path: str | None = None) -> str | None:
        """Generate an image from a text prompt and return the file path."""
        if not self._load():
            return None
        try:
            out_path = output_path or str(Path(tempfile.gettempdir()) / "dpi_image.png")
            # Limit inference steps for speed on server
            image = self._pipeline(prompt, num_inference_steps=20).images[0]
            image.save(out_path)
            logger.info("Image saved: %s", out_path)
            return out_path
        except Exception as exc:
            logger.warning("Image generation failed: %s", exc)
            return None


# Global instance (lazy init)
_image_gen: ImageGenerator | None = None


def get_image_generator() -> ImageGenerator:
    global _image_gen
    if _image_gen is None:
        _image_gen = ImageGenerator()
    return _image_gen
