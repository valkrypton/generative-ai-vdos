"""Wan image-to-video via Alibaba Model Studio (DashScope REST API).

Needs DASHSCOPE_API_KEY (and optionally DASHSCOPE_API_URL for a workspace
endpoint). New intl (Singapore) accounts get ~1650s of free video generation
credit for 90 days; after that roughly $0.10-0.25 per 5s clip.

Model/resolution/duration are fixed constants below — clips are capped at
5 seconds to keep credit use predictable while testing.
"""
import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

from ..env import dashscope_base_url
from .base import VideoProvider

# Quality tiers — verify model IDs in your DashScope console if one errors.
QUALITY_MODELS = {
    "flash": "wan2.2-i2v-flash",   # default: fast, basic motion
    "turbo": "wan2.1-i2v-turbo",   # better prompt-following, ~same cost
    "plus":  "wan2.1-i2v-plus",    # best quality, slower
}
RESOLUTION = "720P"
MAX_DURATION = 5            # seconds — hard cap per clip


class WanProvider(VideoProvider):
    name = "wan-i2v"

    def __init__(self, quality: str = "flash") -> None:
        if quality not in QUALITY_MODELS:
            raise ValueError(f"wan quality must be flash|turbo|plus, got '{quality}'")
        self._model = QUALITY_MODELS[quality]
        self._quality = quality

    def available(self) -> bool:
        return bool(os.environ.get("DASHSCOPE_API_KEY"))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}"}

    def submit(self, prompt: str, image_path: Path) -> str:
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()
        body = {
            "model": self._model,
            "input": {
                "prompt": prompt,
                "img_url": f"data:image/png;base64,{img_b64}",
            },
            "parameters": {
                "resolution": RESOLUTION,
                "duration": MAX_DURATION,
                "prompt_extend": True,
                "watermark": False,
            },
        }
        req = urllib.request.Request(
            f"{dashscope_base_url()}/services/aigc/video-generation/video-synthesis",
            data=json.dumps(body).encode(),
            headers={**self._headers(), "Content-Type": "application/json",
                     "X-DashScope-Async": "enable"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
        return out["output"]["task_id"]

    def poll(self, task_id: str) -> Optional[str]:
        req = urllib.request.Request(f"{dashscope_base_url()}/tasks/{task_id}", headers=self._headers())
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read())["output"]
        status = out["task_status"]
        if status == "SUCCEEDED":
            return out["video_url"]
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"wan task {status}: {out.get('message', out)}")
        return None  # PENDING / RUNNING

    def download(self, url: str, out_path: Path) -> None:
        urllib.request.urlretrieve(url, out_path)

    def generate(self, prompt: str, image_path: Path, out_path: Path, api_key=None) -> None:
        task_id = self.submit(prompt, image_path)
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            time.sleep(15)
            url = self.poll(task_id)
            if url:
                self.download(url, out_path)
                return
        raise RuntimeError(f"wan task timed out after 15 min (task_id={task_id})")
