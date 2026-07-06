"""(Re)render composition scenes for an existing work dir.

Usage:
    python -m pipeline.compose output/<slug>     # render all compose scenes
"""
import argparse
from pathlib import Path

from ..env import load_env
from ..schema import ShotPlan
from . import render_compositions


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", nargs="?", default=None,
                        help="output/<name> dir (default: the most recent one)")
    args = parser.parse_args()

    from ..run import latest_work_dir
    work_dir = Path(args.work_dir) if args.work_dir else latest_work_dir()
    print(f"video folder: {work_dir}")
    plan = ShotPlan.model_validate_json((work_dir / "shot_plan.json").read_text())
    rendered = render_compositions(plan, work_dir)
    if rendered:
        print(f"Done: rendered {len(rendered)} composition scene(s)")
    else:
        print("No compose scenes in this plan.")


if __name__ == "__main__":
    main()
