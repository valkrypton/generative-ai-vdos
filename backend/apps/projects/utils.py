from pathlib import Path

from django.conf import settings


def get_work_dir(project):
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)
