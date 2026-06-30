"""Replicate image backend (~$0.003/image for Flux Schnell). Needs
REPLICATE_API_TOKEN, the replicate package, and the model id in .env
(REPLICATE_IMAGE_MODEL) — no model is hardcoded."""
import os
import urllib.request

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

    def generate(self, prompt: str, query: str | None = None,
                 negative: str | None = None, api_key=None,
                 model: str | None = None, on_preview_url=None) -> bytes:
        import replicate as replicate_pkg

        model = model or os.environ.get("REPLICATE_IMAGE_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "no Replicate image model set — put REPLICATE_IMAGE_MODEL in .env")
        client = replicate_pkg.Client(api_token=api_key.decrypt()) if api_key else replicate_pkg
        output = client.run(
            model,
            input={"prompt": prompt, "aspect_ratio": "16:9", "output_format": "png"},
        )
        url = str(output[0]) if isinstance(output, list) else str(output)
        with urllib.request.urlopen(url, timeout=60) as resp:
            return resp.read()
