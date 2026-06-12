"""Animate scene stills for an existing work dir — all scenes or a single one.

Usage:
    python -m pipeline.video output/<slug>             # all scenes missing a clip
    python -m pipeline.video output/<slug> --scene 7   # one scene
    python -m pipeline.video output/<slug> --backend wan-i2v
"""
import argparse
from pathlib import Path

from ..env import load_env
from ..schema import ShotPlan
from . import PROVIDERS, _motion_prompt, animate_scenes, get_provider


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", help="output/<slug> dir containing shot_plan.json + images/")
    parser.add_argument("--scene", type=int, default=None, help="Animate only this scene index (0-based)")
    parser.add_argument("--backend", default=None,
                        choices=[p.name for p in PROVIDERS], help="Force a specific backend")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
    images_dir = work_dir / "images"
    out_dir = work_dir / "video"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scene is not None:
        provider = get_provider(args.backend)
        out = out_dir / f"scene_{args.scene:02d}.mp4"
        provider.generate(_motion_prompt(plan.scenes[args.scene]),
                          images_dir / f"scene_{args.scene:02d}.png", out)
        print(f"animated {out} via {provider.name}")
    else:
        animate_scenes(plan, images_dir, out_dir, backend=args.backend)


if __name__ == "__main__":
    main()
