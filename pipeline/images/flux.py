"""Replicate image backend (~$0.003/image for Flux Schnell). Needs
REPLICATE_API_TOKEN, the replicate package, and the model id in .env
(REPLICATE_IMAGE_MODEL) — no model is hardcoded."""
import os
import urllib.request
from pathlib import Path
from typing import Optional

from .base import ImageProvider


class FluxProvider(ImageProvider):
    name = "flux-schnell"
    requires = "REPLICATE_API_TOKEN (+ pip install replicate)"

    def available(self) -> bool:
        if not os.environ.get("REPLICATE_API_TOKEN"):
            return False
        try:
            import replicate  # noqa: F401
        except ImportError:
            return False
        return True

    def generate(self, prompt: str, path: Path, query: Optional[str] = None,
                 negative: Optional[str] = None, api_key=None) -> None:
        import replicate

        model = os.environ.get("REPLICATE_IMAGE_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "no Replicate image model set — put REPLICATE_IMAGE_MODEL in .env")
        output = replicate.run(
            model,
            input={"prompt": prompt, "aspect_ratio": "16:9", "output_format": "png"},
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        urllib.request.urlretrieve(url, path)
