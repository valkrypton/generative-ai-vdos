import json
import logging

from django.conf import settings
from django.db import transaction

from apps.accounts.models import UserProfile

from .constants import Level, Stage
from .models import JobLog, Project

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    broker_url = getattr(settings, "CELERY_BROKER_URL", None)
    if not broker_url:
        return None
    try:
        import redis
    except ImportError:
        logger.warning("redis package not installed — publish_event will log only")
        return None
    try:
        _redis_client = redis.from_url(broker_url)
        _redis_client.ping()
        return _redis_client
    except Exception:
        logger.debug("Redis unavailable — publish_event will log only")
        _redis_client = None
        return None


def publish_event(project_id, stage, level, message, **extra):
    JobLog.objects.create(
        project_id=project_id, stage=stage, level=level, message=message,
    )

    client = _get_redis()
    if client is None:
        return

    payload = json.dumps({
        "project_id": str(project_id),
        "stage": stage,
        "level": level,
        "message": message,
        **extra,
    })
    try:
        client.publish(f"project:{project_id}:events", payload)
    except Exception:
        logger.debug("Redis publish failed for project %s", project_id)


class ProjectService:
    @staticmethod
    @transaction.atomic
    def create(owner: UserProfile, prompt: str, **kwargs) -> Project:
        project = Project.objects.create(owner=owner, prompt=prompt, **kwargs)
        JobLog.objects.create(
            project=project,
            stage=Stage.PLAN,
            level=Level.INFO,
            message="Project created.",
        )
        return project
