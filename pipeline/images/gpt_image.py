"""OpenAI image backend (~$0.01-0.02/image at low quality). Needs OPENAI_API_KEY
and the model id in .env (OPENAI_IMAGE_MODEL) — no model is hardcoded."""
import base64
import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image

from .base import ImageProvider
from .util import fit_cover


def _model() -> str:
    """Image model id — from .env (OPENAI_IMAGE_MODEL). No hardcoded default."""
    model = os.environ.get("OPENAI_IMAGE_MODEL", "").strip()
    if not model:
        raise RuntimeError("no OpenAI image model set — put OPENAI_IMAGE_MODEL in .env")
    return model


class GptImageProvider(ImageProvider):
    name = "gpt-image-1"
    requires = "OPENAI_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def generate(self, prompt: str, path: Path, query: Optional[str] = None,
                 negative: Optional[str] = None, api_key=None) -> None:
        from openai import OpenAI

        # No negative_prompt param here, but the model follows instructions well
        # — fold negatives into the prompt as an explicit "do not include".
        if negative:
            prompt = f"{prompt}. Do not include: {negative}."
        client = OpenAI()
        result = client.images.generate(
            model=_model(), prompt=prompt, size="1536x1024", quality="low", n=1,
        )
        img = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")
        fit_cover(img).save(path)

    def edit(self, prompt: str, reference, path: Path,
             negative: Optional[str] = None) -> None:
        """Build the scene on top of one or more reference images. `reference` is
        a single Path or a list of Paths."""
        from openai import OpenAI

        if negative:
            prompt = f"{prompt}. Do not include: {negative}."
        refs = list(reference) if isinstance(reference, (list, tuple)) else [reference]
        client = OpenAI()
        handles = [open(Path(r), "rb") for r in refs]
        try:
            result = client.images.edit(
                model=_model(),
                image=handles if len(handles) > 1 else handles[0],
                prompt=prompt, size="1536x1024", n=1,
            )
        finally:
            for h in handles:
                h.close()
        img = Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")
        fit_cover(img).save(path)
