from django.db import transaction
from apps.accounts.models import UserProfile
from .models import Project, JobLog
from .constants import Stage, Level


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
