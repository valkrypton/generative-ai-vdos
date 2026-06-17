from pathlib import Path

from django.conf import settings

from apps.projects.models import JobLog


def get_work_dir(project):
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)


def log_event(project_id, stage, level, message):
    JobLog.objects.create(
        project_id=project_id, stage=stage, level=level, message=message,
    )
