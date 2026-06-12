"""Pipeline runner. Resumable: each stage records completion in state.json,
so a re-run skips finished stages instead of re-burning credits.

Usage:
    python -m pipeline.run "Why octopuses have three hearts"
    # review/edit output/<slug>/shot_plan.json, then re-run the same command
    python -m pipeline.run "Why octopuses have three hearts" --approve
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from .schema import ShotPlan

STAGES = ["plan", "images", "animate", "voice", "assemble"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def load_state(work_dir: Path) -> dict:
    f = work_dir / "state.json"
    return json.loads(f.read_text()) if f.exists() else {"done": []}


def save_state(work_dir: Path, state: dict) -> None:
    (work_dir / "state.json").write_text(json.dumps(state, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Topic -> finished YouTube video")
    parser.add_argument("topic", help="Topic or rough script")
    parser.add_argument("--approve", action="store_true",
                        help="Proceed past the shot-plan review gate")
    parser.add_argument("--voice", default="en-US-AndrewNeural")
    default_model = "claude-haiku-4-5" if os.environ.get("ANTHROPIC_API_KEY") else "gpt-4o-mini"
    parser.add_argument("--model", default=default_model)
    parser.add_argument("--out", default="output")
    parser.add_argument("--music-dir", default="music")
    parser.add_argument("--name", default=None,
                        help="Output folder name (default: slug of the topic text)")
    parser.add_argument("--image-backend", default=None,
                        help="Force an image provider (see pipeline/images: "
                             "flux-schnell, gpt-image-1, pexels, placeholder)")
    parser.add_argument("--animate", action="store_true",
                        help="Animate scene stills into video clips (needs a video "
                             "backend, e.g. DASHSCOPE_API_KEY for Wan)")
    parser.add_argument("--video-backend", default=None,
                        help="Force a video provider (see pipeline/video: wan-i2v); "
                             "implies --animate")
    parser.add_argument("--until", choices=STAGES, default=None,
                        help="Stop after this stage (step-by-step runs)")
    args = parser.parse_args()

    work_dir = Path(args.out) / (args.name or slugify(args.topic))
    work_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(work_dir)
    plan_file = work_dir / "shot_plan.json"

    # ---- Stage 1: shot plan ----
    if "plan" not in state["done"]:
        from .script_agent import generate_shot_plan
        print(f"stage: plan ({args.model})")
        plan = generate_shot_plan(args.topic, model=args.model)
        plan_file.write_text(plan.model_dump_json(indent=2))
        state["done"].append("plan")
        save_state(work_dir, state)
        print(f"  wrote {plan_file} ({len(plan.scenes)} scenes)")

    plan = ShotPlan.model_validate_json(plan_file.read_text())
    if args.until == "plan":
        print(f"stopped after plan (--until): review {plan_file}")
        return

    # ---- Review gate ----
    if not args.approve and "approved" not in state["done"]:
        print(f"\nReview gate: inspect/edit {plan_file}")
        print("Then re-run with --approve to generate assets.")
        sys.exit(0)
    if "approved" not in state["done"]:
        state["done"].append("approved")
        save_state(work_dir, state)

    # ---- Stage 2: images ----
    if "images" not in state["done"]:
        from .images import generate_images
        print("stage: images")
        generate_images(plan, work_dir / "images", backend=args.image_backend)
        state["done"].append("images")
        save_state(work_dir, state)
    if args.until == "images":
        print("stopped after images (--until)")
        return

    # ---- Stage 2.5: animate (optional) ----
    if (args.animate or args.video_backend) and "animate" not in state["done"]:
        from .video import animate_scenes
        print("stage: animate")
        animate_scenes(plan, work_dir / "images", work_dir / "video",
                       backend=args.video_backend)
        state["done"].append("animate")
        save_state(work_dir, state)
    if args.until == "animate":
        print("stopped after animate (--until)")
        return

    # ---- Stage 3: voiceover ----
    if "voice" not in state["done"]:
        from .voiceover import generate_voiceover
        print("stage: voiceover (edge-tts)")
        generate_voiceover(plan, work_dir / "audio", voice=args.voice)
        state["done"].append("voice")
        save_state(work_dir, state)
    if args.until == "voice":
        print("stopped after voice (--until)")
        return

    # ---- Stage 4: assembly ----
    if "assemble" not in state["done"]:
        from .assemble import assemble, pick_music
        print("stage: assemble (ffmpeg)")
        music = pick_music(Path(args.music_dir), plan.music_mood)
        print(f"  music: {music if music else 'none (music/ folder empty)'}")
        final = assemble(plan, work_dir, music_path=music)
        state["done"].append("assemble")
        save_state(work_dir, state)
        print(f"\nDone: {final}")
        print(f"Title: {plan.title}")
    else:
        print(f"Already complete: {work_dir / 'final.mp4'}")


if __name__ == "__main__":
    main()
