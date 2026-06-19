import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.accounts.models import UserAPIKey
from apps.projects.constants import Capability, Level, Status
from apps.projects.models import LLMModel, Project, Scene
from apps.projects.services import publish_event
from pipeline.script_agent import consistency_review, polish_image_prompts

logger = logging.getLogger(__name__)


def get_work_dir(project):
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)


def resolve_secure_key(owner, provider):
    try:
        return UserAPIKey.objects.get(
            owner=owner, provider=provider,
        ).get_secure_key()
    except UserAPIKey.DoesNotExist:
        return None


def resolve_plan_model(project):
    llm = project.plan_model or LLMModel.objects.filter(
        capability=Capability.PLAN, is_default=True, is_active=True,
    ).select_related("provider").first()

    if not llm:
        raise RuntimeError("No plan model assigned and no default plan model configured.")

    return llm


def polish_plan(plan, model_id, provider_code, secure_key):
    plan = polish_image_prompts(plan, model=model_id,
                                provider=provider_code, api_key=secure_key)
    plan = consistency_review(plan, model=model_id,
                              provider=provider_code, api_key=secure_key)
    return plan


def save_plan(project, plan):
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


def fetch_project_for_plan(project_id):
    try:
        return Project.objects.select_related(
            "plan_model", "plan_model__provider", "owner",
        ).get(id=project_id)
    except Project.DoesNotExist:
        logger.error("Project %s not found, aborting stage", project_id)
        return None


def handle_transient_error(task, project, project_id, stage, exc):
    retries_left = task.max_retries - task.request.retries
    if retries_left > 0:
        logger.warning("%s stage transient error, %d retries left: %s", stage, retries_left, exc)
        raise
    fail_project(project, project_id, stage, exc)


def fail_project(project, project_id, stage, exc):
    error_type = type(exc).__name__
    error_message = f"[{error_type}] {exc}"
    logger.error("%s stage failed: %s", stage, error_message)
    project.error = error_message[:2000]
    project.save(update_fields=["error", "updated_at"])
    project.transition_status(Status.FAILED)
    publish_event(project_id, stage, Level.ERROR, error_message[:500])
