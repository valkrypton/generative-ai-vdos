import logging

from celery import shared_task
from django.db import transaction

from apps.projects.constants import ImageStatus, Level, Stage, Status
from apps.projects.models import Project, Scene
from apps.projects.services import publish_event
from apps.projects.utils import get_work_dir

logger = logging.getLogger(__name__)


@shared_task(
    soft_time_limit=5 * 60,
    time_limit=6 * 60,
)
def run_plan_stage(project_id):
    from pipeline.script_agent import (
        consistency_review,
        generate_shot_plan,
        polish_image_prompts,
    )

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        logger.error("Project %s not found, aborting plan stage", project_id)
        return {"project_id": str(project_id)}

    try:
        project.transition_status(Status.PLANNING)

        publish_event(project_id, Stage.PLAN, Level.INFO, "Generating shot plan")
        plan = generate_shot_plan(project.prompt)

        publish_event(project_id, Stage.PLAN, Level.INFO, "Polishing image prompts")
        plan = polish_image_prompts(plan)

        publish_event(project_id, Stage.PLAN, Level.INFO, "Running consistency review")
        plan = consistency_review(plan)

        with transaction.atomic():
            project.shot_plan = plan.model_dump()
            project.title = plan.title
            project.save(update_fields=["shot_plan", "title", "updated_at"])

            project.scenes.all().delete()
            Scene.objects.bulk_create([
                Scene(
                    project=project,
                    index=i,
                    narration=scene.narration,
                    media_prompt=scene.image_prompt,
                    on_screen_text=scene.on_screen_text or "",
                    negative_prompt=scene.negative_prompt or "",
                    animate=scene.animate,
                )
                for i, scene in enumerate(plan.scenes)
            ])

        publish_event(project_id, Stage.PLAN, Level.INFO, f"Shot plan ready — {len(plan.scenes)} scenes")
        project.transition_status(Status.REVIEW)

    except Exception as exc:
        project.error = str(exc)[:2000]
        project.save(update_fields=["error", "updated_at"])
        project.transition_status(Status.FAILED)
        publish_event(project_id, Stage.PLAN, Level.ERROR, str(exc)[:500])
        raise

    return {"project_id": str(project_id)}


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
    publish_event(project_id, Stage.IMAGES, Level.INFO, f"Generating image for scene {scene_index}",
                  scene_index=scene_index)

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual image backend
        scene.image_status = ImageStatus.DONE
        scene.save(update_fields=["image_status", "updated_at"])
        publish_event(project_id, Stage.IMAGES, Level.INFO, f"Scene {scene_index} image done",
                      scene_index=scene_index)
    except (ConnectionError, TimeoutError):
        scene.image_status = ImageStatus.FAILED
        scene.save(update_fields=["image_status", "updated_at"])
        publish_event(project_id, Stage.IMAGES, Level.ERROR, f"Scene {scene_index} failed (will retry)",
                      scene_index=scene_index)
        raise
    except Exception as exc:
        scene.image_status = ImageStatus.FAILED
        scene.save(update_fields=["image_status", "updated_at"])
        publish_event(project_id, Stage.IMAGES, Level.ERROR, f"Scene {scene_index} failed: {exc}",
                      scene_index=scene_index)
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
    publish_event(project_id, Stage.VOICE, Level.INFO, "Generating voiceover")

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual TTS backend
        publish_event(project_id, Stage.VOICE, Level.INFO, "Voiceover done")
    except (ConnectionError, TimeoutError):
        publish_event(project_id, Stage.VOICE, Level.ERROR, "Voiceover failed (will retry)")
        raise
    except Exception as exc:
        publish_event(project_id, Stage.VOICE, Level.ERROR, f"Voiceover failed: {exc}")
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
    publish_event(project_id, Stage.ASSEMBLE, Level.INFO, "Assembling final video")

    try:
        work_dir = get_work_dir(project)
        work_dir.mkdir(parents=True, exist_ok=True)
        # TODO: call actual FFmpeg assembly
        project.transition_status(Status.DONE)
        publish_event(project_id, Stage.ASSEMBLE, Level.INFO, "Assembly complete")
    except (ConnectionError, TimeoutError):
        publish_event(project_id, Stage.ASSEMBLE, Level.ERROR, "Assembly failed (will retry)")
        raise
    except Exception as exc:
        publish_event(project_id, Stage.ASSEMBLE, Level.ERROR, f"Assembly failed: {exc}")
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
        publish_event(project_id, Stage.IMAGES, Level.ERROR, f"Pipeline failed (task {task_id})")
    except Project.DoesNotExist:
        logger.warning("Project %s not found when marking failed", project_id)
