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
            scene_voice = scene.voice or voice
            await _synth_scene(scene.narration, scene_voice, mp3, words)
            mp3_paths.append(mp3)
            print(f"  voice: scene {i + 1}/{len(plan.scenes)} ({scene_voice})")

    asyncio.run(run_all())
    return mp3_paths


def main() -> None:
    """CLI: python -m pipeline.voiceover output/<slug> [--voice NAME]"""
    import argparse

    from .env import load_env
    load_env()
    parser = argparse.ArgumentParser(description="Generate voiceover for an existing work dir")
    parser.add_argument("work_dir", nargs="?", default=None,
                        help="output/<name> dir (default: the most recent one)")
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                        help="Narrator voice; per-scene 'voice' in shot_plan.json overrides")
    args = parser.parse_args()

    from .run import latest_work_dir
    work_dir = Path(args.work_dir) if args.work_dir else latest_work_dir()
    print(f"video folder: {work_dir}")
    plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
    generate_voiceover(plan, work_dir / "audio", voice=args.voice)


if __name__ == "__main__":
    main()
