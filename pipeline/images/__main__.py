"""(Re)generate images for an existing work dir — all scenes or a single one.

Usage:
    python -m pipeline.images output/<slug>                 # all scenes
    python -m pipeline.images output/<slug> --scene 7       # one scene, e.g. after editing its image_prompt
    python -m pipeline.images output/<slug> --backend pexels
"""
import argparse
import os
from pathlib import Path

from ..env import load_env
from ..schema import ShotPlan
from . import generate_images, generate_scene_image, get_provider


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", nargs="?", default=None,
                        help="output/<name> dir (default: the most recent one)")
    parser.add_argument("--scene", type=int, default=None, help="Regenerate only this scene index (0-based)")
    parser.add_argument("--backend", default=os.environ.get("IMAGE_BACKEND"),
                        help="Image backend (.env: IMAGE_BACKEND; qwen | openai | "
                             "flux | stock | placeholder)")
    args = parser.parse_args()

    from ..run import latest_work_dir
    work_dir = Path(args.work_dir) if args.work_dir else latest_work_dir()
    print(f"video folder: {work_dir}")
    plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
    out_dir = work_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scene is not None:
        primary = get_provider(args.backend)
        path, used = generate_scene_image(plan, args.scene, out_dir, primary,
                                          fallback=args.backend is None)
        print(f"regenerated {path} via {used.name}")
    else:
        generate_images(plan, out_dir, backend=args.backend)


if __name__ == "__main__":
    main()
