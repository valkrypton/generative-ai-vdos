import os
import uuid as _uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import UserAPIKey, UserProfile
from apps.core.models import Provider
from apps.projects.models import Project
from apps.projects.utils import MissingAPIKeyError, get_work_dir, resolve_secure_key
from pipeline.secure import get_fernet


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

        expected = Path(settings.BASE_DIR).parent / "workdirs" / str(project.owner_id) / str(project.id)
        self.assertEqual(result, expected)


class ResolveSecureKeyTest(TestCase):
    def setUp(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        get_fernet.cache_clear()
        self.user = UserProfile.objects.create(cognito_sub="rsk-sub", email="rsk@example.com")
        self.provider = Provider.objects.create(code="openai", name="OpenAI")

    def tearDown(self):
        get_fernet.cache_clear()

    def test_raises_when_no_key_configured(self):
        with self.assertRaises(MissingAPIKeyError):
            resolve_secure_key(self.user, self.provider)

    def test_returns_secure_key_when_configured(self):
        key = UserAPIKey(owner=self.user, provider=self.provider)
        key.set_api_key("sk-test-key-12345678")
        key.save()
        result = resolve_secure_key(self.user, self.provider)
        self.assertEqual(result.decrypt(), "sk-test-key-12345678")
