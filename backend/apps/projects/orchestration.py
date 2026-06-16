from celery import chord, group

from apps.projects.tasks import (
    mark_pipeline_failed,
    run_assemble_stage,
    run_image_stage,
    run_voice_stage,
)


def enqueue_pipeline(project_id, scene_count):
    """Dispatch the assets pipeline: images (parallel) | voice | assemble.

    Called by the approve API endpoint after creating Scene rows.
    """
    pid = str(project_id)
    image_tasks = group(run_image_stage.s(pid, i) for i in range(scene_count))
    post_images = run_voice_stage.si(pid) | run_assemble_stage.si(pid)
    pipeline = chord(image_tasks)(
        post_images,
        link_error=mark_pipeline_failed.s(project_id=pid),
    )
    return pipeline
