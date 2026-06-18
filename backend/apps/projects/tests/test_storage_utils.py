import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import _get_provider
from apps.storage.local_storage import LocalStorageProvider
from apps.storage.s3_storage import S3StorageProvider
from apps.storage.base_storage import BaseStorageProvider
from apps.storage import storage_provider

def _owner(sub="sub-utils"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@test.com")


def _project(owner=None):
    return Project.objects.create(owner=owner or _owner(), prompt="utils test")


def _tmp_file(content: bytes = b"\x89PNG\r\n", suffix: str = ".png") -> Path:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    f.write(content)
    f.flush()
    return Path(f.name)


class StorageProviderAbstractionTest(TestCase):
    """Ensure the class hierarchy is correct without hitting storage backends."""

    def test_base_is_abstract(self):
        self.assertTrue(hasattr(BaseStorageProvider, "__abstractmethods__"))

    def test_local_is_concrete_subclass(self):
        self.assertTrue(issubclass(LocalStorageProvider, BaseStorageProvider))
        p = LocalStorageProvider()
        self.assertIsInstance(p, BaseStorageProvider)

    def test_s3_is_concrete_subclass(self):
        self.assertTrue(issubclass(S3StorageProvider, BaseStorageProvider))
        p = S3StorageProvider(expire=1800)
        self.assertIsInstance(p, BaseStorageProvider)

    def test_get_provider_returns_local_in_tests(self):
        # InMemoryStorage is active in tests — provider must be Local
        self.assertIsInstance(_get_provider(), LocalStorageProvider)


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
