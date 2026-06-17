from django.conf import settings
from celery import group

from apps.projects.tasks import (
    mark_pipeline_failed,
    run_assemble_stage,
    run_image_stage,
    run_voice_stage,
)


def run_images(project_id, scene_count):
    """Dispatch image generation for all scenes (parallel).

    Returns after completion. User reviews images before triggering voice.
    """
    pid = str(project_id)
    image_tasks = group(run_image_stage.s(pid, i) for i in range(scene_count))

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        try:
            image_tasks.apply()
        except Exception:
            mark_pipeline_failed("eager-mode", project_id=pid)
        return None

    return image_tasks.apply_async(
        link_error=mark_pipeline_failed.s(project_id=pid),
    )


def run_voice(project_id):
    """Dispatch voiceover generation.

    User reviews voice before triggering assembly.
    """
    pid = str(project_id)

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        try:
            run_voice_stage.apply(args=[pid])
        except Exception:
            mark_pipeline_failed("eager-mode", project_id=pid)
        return None

    return run_voice_stage.apply_async(
        args=[pid],
        link_error=mark_pipeline_failed.s(project_id=pid),
    )


def run_assembly(project_id):
    """Dispatch final video assembly."""
    pid = str(project_id)

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        try:
            run_assemble_stage.apply(args=[pid])
        except Exception:
            mark_pipeline_failed("eager-mode", project_id=pid)
        return None

    return run_assemble_stage.apply_async(
        args=[pid],
        link_error=mark_pipeline_failed.s(project_id=pid),
    )
