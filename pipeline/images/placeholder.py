"""Gradient placeholder cards — always available, $0, lets the pipeline run with no keys."""
import hashlib
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from .base import ImageProvider
from .util import WIDTH, HEIGHT


class PlaceholderProvider(ImageProvider):
    name = "placeholder"
    cost_note = "$0, no API"

    def available(self) -> bool:
        return True

    def generate(self, prompt: str, path: Path, query: Optional[str] = None) -> None:
        h = hashlib.sha256(prompt.encode()).digest()
        top = (h[0] % 120 + 20, h[1] % 120 + 20, h[2] % 120 + 40)
        bottom = (h[3] % 120 + 20, h[4] % 120 + 40, h[5] % 120 + 20)
        img = Image.new("RGB", (WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / HEIGHT
            img.paste(
                tuple(int(top[c] * (1 - t) + bottom[c] * t) for c in range(3)),
                (0, y, WIDTH, y + 1),
            )
        draw = ImageDraw.Draw(img)
        wrapped = textwrap.fill(prompt, width=60)
        draw.multiline_text((80, HEIGHT - 280), wrapped, fill=(255, 255, 255, 180))
        img.save(path)
