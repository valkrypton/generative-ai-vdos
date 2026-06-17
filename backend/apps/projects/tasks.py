import logging

from celery import shared_task

from apps.projects.constants import ImageStatus, Status
from apps.projects.models import Project, Scene
from apps.projects.utils import get_work_dir, log_event

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=10 * 60,
    time_limit=12 * 60,
)
def run_image_stage(self, project_id, scene_index):
    project = Project.objects.get(id=project_id)
    scene = Scene.objects.get(project_id=project_id, index=scene_index)

    scene.image_status = ImageStatus.RUNNING
    scene.save(update_fields=["image_status", "updated_at"])
    log_event(project_id, "images", "info", f"Generating image for scene {scene_index}")

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual image backend
        scene.image_status = ImageStatus.DONE
        scene.save(update_fields=["image_status", "updated_at"])
        log_event(project_id, "images", "info", f"Scene {scene_index} image done")
    except (ConnectionError, TimeoutError):
        scene.image_status = ImageStatus.FAILED
        scene.save(update_fields=["image_status", "updated_at"])
        log_event(project_id, "images", "error", f"Scene {scene_index} failed (will retry)")
        raise
    except Exception as exc:
        scene.image_status = ImageStatus.FAILED
        scene.save(update_fields=["image_status", "updated_at"])
        log_event(project_id, "images", "error", f"Scene {scene_index} failed: {exc}")
        raise

    return {"project_id": project_id, "scene_index": scene_index}


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=15 * 60,
    time_limit=18 * 60,
)
def run_voice_stage(self, project_id):
    project = Project.objects.get(id=project_id)
    log_event(project_id, "voice", "info", "Generating voiceover")

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual TTS backend
        log_event(project_id, "voice", "info", "Voiceover done")
    except (ConnectionError, TimeoutError):
        log_event(project_id, "voice", "error", "Voiceover failed (will retry)")
        raise
    except Exception as exc:
        log_event(project_id, "voice", "error", f"Voiceover failed: {exc}")
        raise

    return {"project_id": project_id}


@shared_task(
    bind=True,
    max_retries=2,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=20 * 60,
    time_limit=25 * 60,
)
def run_assemble_stage(self, project_id):
    project = Project.objects.get(id=project_id)
    log_event(project_id, "assemble", "info", "Assembling final video")

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual FFmpeg assembly
        project.transition_status(Status.DONE)
        log_event(project_id, "assemble", "info", "Assembly complete")
    except (ConnectionError, TimeoutError):
        log_event(project_id, "assemble", "error", "Assembly failed (will retry)")
        raise
    except Exception as exc:
        log_event(project_id, "assemble", "error", f"Assembly failed: {exc}")
        raise

    return {"project_id": project_id}


@shared_task
def mark_pipeline_failed(task_id, project_id):
    """Error callback for chord/chain — marks the project as FAILED."""
    logger.error("Pipeline task %s failed for project %s", task_id, project_id)
    try:
        project = Project.objects.get(id=project_id)
        project.transition_status(Status.FAILED)
        project.error = f"Pipeline task {task_id} failed"
        project.save(update_fields=["error", "updated_at"])
        log_event(project_id, "images", "error", f"Pipeline failed (task {task_id})")
    except Project.DoesNotExist:
        logger.warning("Project %s not found when marking failed", project_id)
