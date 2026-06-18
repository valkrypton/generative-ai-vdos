import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import StorageProvider, storage_provider


def _owner(sub="sub-utils"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@test.com")


def _project(owner=None):
    return Project.objects.create(owner=owner or _owner(), prompt="utils test")


def _tmp_file(content: bytes = b"\x89PNG\r\n", suffix: str = ".png") -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(content)
        f.flush()
        return Path(f.name)


class StorageProviderBackendTest(TestCase):
    """The single provider resolves its backend by name from STORAGES."""

    def test_uses_named_backend_from_settings(self):
        self.assertIs(StorageProvider().storage, storages["default"])

    def test_facade_exposes_upload_and_url(self):
        self.assertTrue(callable(storage_provider.upload))
        self.assertTrue(callable(storage_provider.url))


class UploadFileToFieldTest(TestCase):
    def setUp(self):
        self.owner = _owner()
        self.project = _project(owner=self.owner)
        self.scene = Scene.objects.create(project=self.project, index=0)

    def test_upload_sets_field_truthy(self):
        local = _tmp_file()
        storage_provider.upload(self.scene.media_path, local)
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.media_path)

    def test_upload_key_contains_owner_and_project_ids(self):
        local = _tmp_file()
        storage_provider.upload(self.scene.media_path, local)
        self.scene.refresh_from_db()
        self.assertIn(str(self.owner.id), self.scene.media_path.name)
        self.assertIn(str(self.project.id), self.scene.media_path.name)

    def test_upload_with_save_false_does_not_persist(self):
        local = _tmp_file()
        storage_provider.upload(self.scene.media_path, local, save=False)
        fresh = Scene.objects.get(pk=self.scene.pk)
        self.assertFalse(fresh.media_path)


class FieldUrlTest(TestCase):
    def setUp(self):
        self.owner = _owner("sub-url-utils")
        self.project = _project(owner=self.owner)
        self.scene = Scene.objects.create(project=self.project, index=0)

    def test_returns_none_for_empty_field(self):
        self.assertIsNone(storage_provider.url(self.scene.media_path))

    def test_returns_string_after_upload(self):
        self.scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)
        self.scene.refresh_from_db()
        result = storage_provider.url(self.scene.media_path)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
