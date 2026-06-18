"""Qwen text-to-image via Alibaba Model Studio (DashScope REST API).

Uses the same DASHSCOPE_API_KEY (and optional DASHSCOPE_API_URL workspace
endpoint) as the Wan video backend. Model Studio's new-user free quota covers
the qwen-image models, so images are $0 while it lasts.
"""
import base64
import io
import json
import os
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image

from ..env import dashscope_base_url
from .base import ImageProvider
from .util import fit_cover

SIZE = "1664*928"  # native 16:9; fit_cover upscales to 1920x1080
MAX_PROMPT = 1500  # warn before cutting; most models accept well beyond this
MAX_REFS = 3  # cap on reference images sent per edit


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

    def _post(self, model: str, content: list, path: Path,
              parameters: dict) -> None:
        """POST one multimodal-generation request and save the returned image."""
        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }
        req = urllib.request.Request(
            f"{dashscope_base_url()}/services/aigc/multimodal-generation/generation",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read())
        url = out["output"]["choices"][0]["message"]["content"][0]["image"]
        with urllib.request.urlopen(url, timeout=60) as resp:
            img = Image.open(io.BytesIO(resp.read())).convert("RGB")
        fit_cover(img).save(path)

    def generate(self, prompt: str, path: Path, query: Optional[str] = None,
                 negative: Optional[str] = None, api_key=None) -> None:
        if len(prompt) > MAX_PROMPT:
            print(f"  images: WARNING prompt is {len(prompt)} chars, cutting to "
                  f"{MAX_PROMPT} — some detail at the end will be lost")
        self._post(_gen_model(), [{"text": prompt[:MAX_PROMPT]}], path, {
            "size": SIZE,
            "n": 1,
            # qwen-image excels at text rendering and its prompt extender
            # loves adding captions — but captions are burned in later from
            # the TTS timings, so keep generated images text-free.
            "prompt_extend": False,
            "watermark": False,
            "negative_prompt": ("text, words, captions, typography, letters, "
                                "watermark, logo, subtitles"
                                + (f", {negative}" if negative else "")),
        })

    def edit(self, prompt: str, reference, path: Path,
             negative: Optional[str] = None) -> None:
        """Re-render to match prompt while keeping the subject(s) looking the same
        (face, hair, clothing). `reference` is a single Path or a list of Paths
        (up to 3, for multi-character scenes). Free on the qwen-image-2.0 quota."""
        refs = list(reference) if isinstance(reference, (list, tuple)) else [reference]
        content = [{"image": "data:image/png;base64,"
                    + base64.b64encode(Path(r).read_bytes()).decode()}
                   for r in refs[:MAX_REFS]]
        content.append({"text": prompt[:MAX_PROMPT]})
        neg = ("text, words, captions, typography, letters, "
               "watermark, logo, subtitles"
               + (f", {negative}" if negative else ""))
        self._post(_edit_model(), content, path, {
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
            "negative_prompt": neg,
        })
