"""Refine a rough idea into a shot plan, review it in the terminal, iterate with feedback.

Usage:
    # 1. New plan from rough text -> output/<title-slug>/shot_plan.json + summary:
    python -m pipeline.refine "two friends talk about stars at night, urdu voices"
    #    (folder is named from the generated title, e.g. output/stars-at-night/)

    # 2. View the current plan again:
    python -m pipeline.refine output/stars-at-night

    # 3. Revise it with feedback (AI rewrites the plan, keeps the rest intact):
    python -m pipeline.refine output/stars-at-night --change "make the mom younger"

    # 4. When happy, generate:
    python -m pipeline.images output/stars-at-night
"""
import argparse
import json
import os
import sys
from pathlib import Path

from .env import load_env
from .schema import ShotPlan


def print_plan(plan: ShotPlan, work_dir: Path) -> None:
    line = "=" * 72
    print(line)
    print(f"TITLE : {plan.title}")
    print(f"STYLE : {plan.style_prefix}")
    print(f"MUSIC : {plan.music_mood}")
    print(f"LENGTH: ~{len(plan.scenes) * 5}s ({len(plan.scenes)} scenes)")
    for i, s in enumerate(plan.scenes):
        print("-" * 72)
        print(f"scene {i}")
        print(f"  narration : {s.narration}")
        print(f"  image     : {s.image_prompt}")
        if s.motion:
            print(f"  motion    : {s.motion}")
        if s.voice:
            print(f"  voice     : {s.voice}")
        if s.on_screen_text:
            print(f"  overlay   : {s.on_screen_text}")
    print(line)
    print(f"plan file : {work_dir / 'shot_plan.json'}")
    print()
    print("next steps:")
    print(f"  revise : python -m pipeline.refine {work_dir} --change \"<your feedback>\"")
    print(f"  images : python -m pipeline.images {work_dir}")
    print(f"  then   : python -m pipeline.video {work_dir} && "
          f"python -m pipeline.voiceover {work_dir} && python -m pipeline.assemble {work_dir}")


def main() -> None:
    load_env()
    default_model = "claude-haiku-4-5" if os.environ.get("ANTHROPIC_API_KEY") else "gpt-4o-mini"
    parser = argparse.ArgumentParser(
        description="Rough idea -> reviewable shot plan; iterate with --change")
    parser.add_argument("input", help="Rough idea text, or an existing output/<name> dir")
    parser.add_argument("--change", default=None,
                        help="Feedback to revise an existing plan (use with an output dir)")
    parser.add_argument("--name", default=None,
                        help="Output folder name for a new plan (default: timestamp)")
    parser.add_argument("--model", default=default_model)
    args = parser.parse_args()

    in_path = Path(args.input)
    if (in_path / "shot_plan.json").is_file():
        # Existing plan: view, or revise with --change.
        work_dir = in_path
        plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
        if args.change:
            from .script_agent import revise_shot_plan
            print(f"revising plan ({args.model})...")
            plan = revise_shot_plan(plan, args.change, model=args.model)
            (work_dir / "shot_plan.json").write_text(plan.model_dump_json(indent=2))
    else:
        # New plan from rough text.
        if args.change:
            sys.exit("--change needs an existing output dir, e.g. "
                     "python -m pipeline.refine output/my-video --change \"...\"")
        import time

        from .run import slugify
        from .script_agent import generate_shot_plan
        print(f"generating plan ({args.model})...")
        plan = generate_shot_plan(args.input, model=args.model)
        # Folder named after the generated title, e.g. output/the-thief-act/
        name = args.name or slugify(plan.title)[:40].strip("-") or time.strftime("%Y%m%d-%H%M%S")
        work_dir = Path("output") / name
        if work_dir.exists():  # same title generated before — keep both
            work_dir = Path("output") / f"{name}-{time.strftime('%H%M%S')}"
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "shot_plan.json").write_text(plan.model_dump_json(indent=2))
        # mark the plan stage done so pipeline.run can also resume this dir
        (work_dir / "state.json").write_text(json.dumps({"done": ["plan"]}, indent=2))

    print_plan(plan, work_dir)


if __name__ == "__main__":
    main()
