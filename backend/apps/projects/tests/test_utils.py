import uuid as _uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.projects.models import Project
from apps.projects.utils import get_work_dir
from apps.users.models import UserProfile


def _make_project():
    uid = _uuid.uuid4().hex[:8]
    user = UserProfile.objects.create(
        cognito_sub=f"sub-svc-{uid}", email=f"svc-{uid}@example.com"
    )
    return Project.objects.create(owner=user, prompt="test prompt")


class GetWorkDirTest(TestCase):
    def test_get_work_dir(self):
        project = _make_project()
        result = get_work_dir(project)

        expected = Path(settings.MEDIA_ROOT) / str(project.owner_id) / str(project.id)
        self.assertEqual(result, expected)
