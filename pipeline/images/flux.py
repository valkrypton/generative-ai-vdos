"""Flux Schnell via Replicate (~$0.003/image). Needs REPLICATE_API_TOKEN + replicate package."""
import os
import urllib.request
from pathlib import Path
from typing import Optional

from .base import ImageProvider


class FluxProvider(ImageProvider):
    name = "flux-schnell"
    cost_note = "~$0.003/image via Replicate"

    def available(self) -> bool:
        if not os.environ.get("REPLICATE_API_TOKEN"):
            return False
        try:
            import replicate  # noqa: F401
        except ImportError:
            return False
        return True

    def generate(self, prompt: str, path: Path, query: Optional[str] = None) -> None:
        import replicate

        output = replicate.run(
            "black-forest-labs/flux-schnell",
            input={"prompt": prompt, "aspect_ratio": "16:9", "output_format": "png"},
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        urllib.request.urlretrieve(url, path)
