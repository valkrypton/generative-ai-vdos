"""Qwen text-to-image via Alibaba Model Studio (DashScope SDK).

Uses the same DASHSCOPE_API_KEY (and optional DASHSCOPE_API_URL workspace
endpoint) as the Wan video backend. Model Studio's new-user free quota covers
the qwen-image models, so images are $0 while it lasts.
"""
import base64
import io
import os
import urllib.request
from pathlib import Path

from PIL import Image
from dashscope import MultiModalConversation

from ..env import configure_dashscope_sdk
from .base import ImageProvider
from .util import to_png_bytes

SIZE = "1664*928"  # native 16:9; fit_cover upscales to 1920x1080
MAX_PROMPT = 1500  # warn before cutting; most models accept well beyond this
MAX_REFS = 3  # cap on reference images sent per edit

_BASE_NEGATIVE = ("text, words, captions, typography, letters, "
                  "watermark, logo, subtitles")


def _negative_prompt(extra: str | None = None) -> str:
    return f"{_BASE_NEGATIVE}, {extra}" if extra else _BASE_NEGATIVE


def _gen_model() -> str:
    """Text-to-image model id — from .env (QWEN_IMAGE_MODEL). No hardcoded
    default: the code is model-agnostic, so the id must be set explicitly.
    Read at call time because .env loads after this module is imported."""
    model = os.environ.get("QWEN_IMAGE_MODEL", "").strip()
    if not model:
        raise RuntimeError("no image model set — put QWEN_IMAGE_MODEL in .env")
    return model


def _edit_model() -> str:
    """Reference-edit model id — from .env (QWEN_EDIT_MODEL), falling back to
    QWEN_IMAGE_MODEL when the same model does both jobs."""
    model = (os.environ.get("QWEN_EDIT_MODEL", "").strip()
             or os.environ.get("QWEN_IMAGE_MODEL", "").strip())
    if not model:
        raise RuntimeError(
            "no edit model set — put QWEN_EDIT_MODEL (or QWEN_IMAGE_MODEL) in .env")
    return model


class QwenImageProvider(ImageProvider):
    name = "qwen-image"
    requires = "DASHSCOPE_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get("DASHSCOPE_API_KEY"))

    def _post(self, model: str, content: list,
              parameters: dict, api_key=None) -> bytes:
        configure_dashscope_sdk()
        key = api_key.decrypt() if api_key else os.environ.get("DASHSCOPE_API_KEY")
        rsp = MultiModalConversation.call(
            model=model,
            messages=[{"role": "user", "content": content}],
            api_key=key,
            **parameters,
        )
        if rsp.status_code != 200:
            raise RuntimeError(f"qwen image failed [{rsp.code}]: {rsp.message}")
        image_url = rsp.output.choices[0].message.content[0]["image"]
        with urllib.request.urlopen(image_url, timeout=60) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        return to_png_bytes(img)

    def generate(self, prompt: str, query: str | None = None,
                 negative: str | None = None, api_key=None,
                 model: str | None = None) -> bytes:
        if len(prompt) > MAX_PROMPT:
            print(f"  images: WARNING prompt is {len(prompt)} chars, cutting to "
                  f"{MAX_PROMPT} — some detail at the end will be lost")
        return self._post(model or _gen_model(), [{"text": prompt[:MAX_PROMPT]}], {
            "size": SIZE,
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
            "negative_prompt": _negative_prompt(negative),
        }, api_key=api_key)

    def edit(self, prompt: str, reference,
             negative: str | None = None, api_key=None,
             model: str | None = None) -> bytes:
        refs = list(reference) if isinstance(reference, (list, tuple)) else [reference]
        content = [{"image": "data:image/png;base64,"
                    + base64.b64encode(Path(r).read_bytes()).decode()}
                   for r in refs[:MAX_REFS]]
        content.append({"text": prompt[:MAX_PROMPT]})
        return self._post(model or _edit_model(), content, {
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
            "negative_prompt": _negative_prompt(negative),
        }, api_key=api_key)
