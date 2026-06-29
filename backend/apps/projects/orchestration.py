from celery import group
from django.conf import settings

from apps.projects.tasks import (
    run_image_stage,
    mark_pipeline_failed,
    run_assemble_stage,
    run_video_stage,
    run_voice_stage,
)


def _is_eager() -> bool:
    return getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)


def _dispatch(canvas, project_id):
    """Run a Celery canvas (single task or group) with eager-mode support.

    In eager mode, exceptions are caught and routed to mark_pipeline_failed
    so that the project is marked FAILED just like the async error callback.
    """
    pid = str(project_id)
    if _is_eager():
        try:
            canvas.apply()
        except Exception:
            mark_pipeline_failed("eager-mode", project_id=pid)
        return None
    return canvas.apply_async(
        link_error=mark_pipeline_failed.s(project_id=pid),
    )


def run_images(project_id, scene_count):
    """Dispatch image generation for all scenes (parallel).

    Returns after completion. User reviews images before triggering voice.
    """
    pid = str(project_id)
    return _dispatch(
        group(run_image_stage.s(pid, i) for i in range(scene_count)),
        project_id,
    )


def run_video(project_id):
    """Dispatch batch video animation for all animate=True scenes."""
    pid = str(project_id)
    return _dispatch(run_video_stage.s(pid), project_id)


def run_voice(project_id):
    """Dispatch voiceover generation.

    User reviews voice before triggering assembly.
    """
    pid = str(project_id)
    return _dispatch(run_voice_stage.s(pid), project_id)


def run_assembly(project_id):
    """Dispatch final video assembly."""
    pid = str(project_id)
    return _dispatch(run_assemble_stage.s(pid), project_id)
