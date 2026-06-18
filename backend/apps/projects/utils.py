from pathlib import Path

from django.conf import settings


def get_work_dir(project):
    return Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)


def resolve_secure_key(owner, provider):
    from apps.accounts.models import UserAPIKey
    try:
        return UserAPIKey.objects.get(
            owner=owner, provider=provider,
        ).get_secure_key()
    except UserAPIKey.DoesNotExist:
        return None
