"""OpenAI gpt-image-1 (~$0.01-0.02/image at low quality). Needs OPENAI_API_KEY."""
import base64
import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image

from .base import ImageProvider
from .util import fit_cover


class GptImageProvider(ImageProvider):
    name = "gpt-image-1"
    requires = "OPENAI_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def generate(self, prompt: str, path: Path, query: Optional[str] = None,
                 negative: Optional[str] = None) -> None:
        from openai import OpenAI

        # gpt-image-1 has no negative_prompt param, but it follows instructions
        # well — fold negatives into the prompt as an explicit "do not include".
        if negative:
            prompt = f"{prompt}. Do not include: {negative}."
        client = OpenAI()
        result = client.images.generate(
            model="gpt-image-1", prompt=prompt, size="1536x1024", quality="low", n=1,
        )
        img = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")
        fit_cover(img).save(path)

    def edit(self, prompt: str, reference: Path, path: Path) -> None:
        """Build the scene on top of a reference photo (real building, person, ...)."""
        from openai import OpenAI

        client = OpenAI()
        with open(reference, "rb") as f:
            result = client.images.edit(
                model="gpt-image-1", image=f, prompt=prompt, size="1536x1024", n=1,
            )
        img = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")
        fit_cover(img).save(path)
