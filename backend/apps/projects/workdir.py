"""Materialize a CLI-style work dir from DB + storage for FFmpeg assembly."""

import shutil
from pathlib import Path

from django.conf import settings

from apps.projects.models import Project
from apps.projects.utils import build_shot_plan, get_work_dir
from pipeline.schema import ShotPlan


def _download_field(field_file, dest: Path) -> None:
    if not field_file:
        raise FileNotFoundError("missing storage file")
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_path = Path(field_file.path).resolve()
    dest = dest.resolve()
    if src_path == dest:
        if not src_path.is_file() or src_path.stat().st_size == 0:
            raise FileNotFoundError(f"empty or missing file: {dest}")
        return
    with field_file.open("rb") as src, dest.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    if dest.stat().st_size == 0:
        raise FileNotFoundError(f"empty file after download: {dest}")


def materialize_work_dir(project: Project) -> tuple[Path, ShotPlan]:
    """Download scene assets into a staging layout expected by pipeline.assemble.

    Uses a ``_assemble`` subdir so we never open storage paths for write in place
    (FileSystemStorage stores images at ``{work_dir}/images/…`` — copying a file
    onto itself truncates it to zero bytes).
    """
    work_dir = get_work_dir(project) / "_assemble"
    images_dir = work_dir / "images"
    audio_dir = work_dir / "audio"
    video_dir = work_dir / "video"
    for d in (images_dir, audio_dir, video_dir):
        d.mkdir(parents=True, exist_ok=True)

    plan = build_shot_plan(project)
    (work_dir / "shot_plan.json").write_text(plan.model_dump_json(indent=2))

    for scene in project.scenes.order_by("index"):
        prefix = f"scene_{scene.index:02d}"
        if not scene.media_path:
            raise FileNotFoundError(f"scene {scene.index} is missing media_path")
        if not scene.audio_path:
            raise FileNotFoundError(f"scene {scene.index} is missing audio_path")

        ext = Path(scene.media_path.name).suffix.lower()
        if ext == ".mp4":
            _download_field(scene.media_path, video_dir / f"{prefix}.mp4")
        else:
            _download_field(scene.media_path, images_dir / f"{prefix}.png")

        _download_field(scene.audio_path, audio_dir / f"{prefix}.mp3")
        if scene.words_path:
            _download_field(scene.words_path, audio_dir / f"{prefix}.words.json")

    return work_dir, plan


def music_root() -> Path:
    return Path(settings.BASE_DIR).parent / "music"
