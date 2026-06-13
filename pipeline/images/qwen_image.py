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

MODEL = "qwen-image-plus"
EDIT_MODEL = "qwen-image-edit"  # reference-image editing: same look in a new scene
SIZE = "1664*928"  # native 16:9; fit_cover upscales to 1920x1080
MAX_PROMPT = 1500  # qwen-image-plus accepts well beyond this; warn before cutting


class QwenImageProvider(ImageProvider):
    name = "qwen-image"

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
                 negative: Optional[str] = None) -> None:
        if len(prompt) > MAX_PROMPT:
            print(f"  images: WARNING prompt is {len(prompt)} chars, cutting to "
                  f"{MAX_PROMPT} — some detail at the end will be lost")
        self._post(MODEL, [{"text": prompt[:MAX_PROMPT]}], path, {
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

    def edit(self, prompt: str, reference: Path, path: Path) -> None:
        """Re-render the reference image to match prompt, keeping the subject's
        look (face, hair, clothing) — qwen-image-edit, free on the same quota."""
        data_uri = "data:image/png;base64," + base64.b64encode(reference.read_bytes()).decode()
        self._post(EDIT_MODEL, [{"image": data_uri}, {"text": prompt[:MAX_PROMPT]}], path, {
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
            "negative_prompt": "text, words, captions, typography, letters, watermark, logo, subtitles",
        })
