"""(Re)generate images for an existing work dir — all scenes or a single one.

Usage:
    python -m pipeline.images output/<slug>                 # all scenes
    python -m pipeline.images output/<slug> --scene 7       # one scene, e.g. after editing its image_prompt
    python -m pipeline.images output/<slug> --backend pexels
"""
import argparse
from pathlib import Path

from ..env import load_env
from ..schema import ShotPlan
from . import PROVIDERS, generate_images, generate_scene_image, get_provider


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", help="output/<slug> dir containing shot_plan.json")
    parser.add_argument("--scene", type=int, default=None, help="Regenerate only this scene index (0-based)")
    parser.add_argument("--backend", default=None,
                        choices=[p.name for p in PROVIDERS], help="Force a specific backend")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
    out_dir = work_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scene is not None:
        primary = get_provider(args.backend)
        path, used = generate_scene_image(plan, args.scene, out_dir, primary)
        print(f"regenerated {path} via {used.name}")
    else:
        generate_images(plan, out_dir, backend=args.backend)


if __name__ == "__main__":
    main()
