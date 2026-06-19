"""Pexels free stock photos. Needs PEXELS_API_KEY (free signup, no billing)."""
import io
import json
import os
import urllib.parse
import urllib.request

from PIL import Image

from .base import ImageProvider
from .util import to_png_bytes


class PexelsProvider(ImageProvider):
    name = "pexels"
    requires = "PEXELS_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get("PEXELS_API_KEY"))

    def generate(self, prompt: str, query: str | None = None,
                 negative: str | None = None, api_key=None,
                 model: str | None = None) -> bytes:
        key = api_key.decrypt() if api_key else os.environ["PEXELS_API_KEY"]
        q = query or prompt
        url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
            {"query": q, "orientation": "landscape", "size": "large", "per_page": 1}
        )
        req = urllib.request.Request(url, headers={"Authorization": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            photos = json.loads(resp.read())["photos"]
        if not photos:
            raise LookupError(f"no pexels results for {q!r}")
        with urllib.request.urlopen(photos[0]["src"]["large2x"], timeout=30) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        return to_png_bytes(img)
