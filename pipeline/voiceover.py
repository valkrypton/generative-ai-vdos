"""Stage 3: per-scene voiceover via edge-tts (free Microsoft neural voices).

edge-tts streams WordBoundary events with timestamps, so caption timing comes
for free — no whisper pass needed.
"""
import asyncio
import json
from pathlib import Path
from typing import List

import edge_tts

from .schema import ShotPlan

DEFAULT_VOICE = "en-US-AndrewNeural"


async def _synth_scene(text: str, voice: str, mp3_path: Path, words_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({
                    "text": chunk["text"],
                    "start": chunk["offset"] / 1e7,      # 100ns ticks -> seconds
                    "duration": chunk["duration"] / 1e7,
                })
    words_path.write_text(json.dumps(words, indent=2))


def generate_voiceover(plan: ShotPlan, out_dir: Path, voice: str = DEFAULT_VOICE) -> List[Path]:
    """Writes scene_NN.mp3 + scene_NN.words.json per scene. Returns mp3 paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3_paths = []

    async def run_all():
        for i, scene in enumerate(plan.scenes):
            mp3 = out_dir / f"scene_{i:02d}.mp3"
            words = out_dir / f"scene_{i:02d}.words.json"
            await _synth_scene(scene.narration, voice, mp3, words)
            mp3_paths.append(mp3)
            print(f"  voice: scene {i + 1}/{len(plan.scenes)}")

    asyncio.run(run_all())
    return mp3_paths
