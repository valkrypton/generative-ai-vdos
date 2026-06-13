"""Animate scene stills — DISABLED (costs DashScope credit).

To re-enable: uncomment the code block at the bottom of this file.
"""
import sys


def main() -> None:
    print("Animation stage is disabled (costs DashScope credit).")
    print("To enable: uncomment the animation code in pipeline/video/__main__.py")
    sys.exit(0)


# --- ANIMATION CODE — uncomment to re-enable ---
#
# import argparse
# from pathlib import Path
#
# from ..env import load_env
# from ..schema import ShotPlan
# from . import PROVIDERS, _motion_prompt, animate_scenes, get_provider
#
#
# def main() -> None:
#     load_env()
#     parser = argparse.ArgumentParser()
#     parser.add_argument("work_dir", nargs="?", default=None)
#     parser.add_argument("--scene", type=int, default=None)
#     parser.add_argument("--backend", default=None, choices=[p.name for p in PROVIDERS])
#     parser.add_argument("--quality", default="flash", choices=["flash", "turbo", "plus"])
#     args = parser.parse_args()
#
#     from ..run import latest_work_dir
#     work_dir = Path(args.work_dir) if args.work_dir else latest_work_dir()
#     print(f"video folder: {work_dir}")
#     plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
#     images_dir = work_dir / "images"
#     out_dir = work_dir / "video"
#     out_dir.mkdir(parents=True, exist_ok=True)
#
#     if args.scene is not None:
#         provider = get_provider(args.backend, quality=args.quality)
#         out = out_dir / f"scene_{args.scene:02d}.mp4"
#         provider.generate(_motion_prompt(plan, plan.scenes[args.scene]),
#                           images_dir / f"scene_{args.scene:02d}.png", out)
#         print(f"animated {out} via {provider.name}")
#     else:
#         animate_scenes(plan, images_dir, out_dir, backend=args.backend, quality=args.quality)


if __name__ == "__main__":
    main()
