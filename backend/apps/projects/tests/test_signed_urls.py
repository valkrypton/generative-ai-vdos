"""
Verifies url() behaviour for the single StorageProvider. On S3 the configured
backend (querystring_auth=True) returns a presigned URL; the provider simply
delegates to its backend's storage.url(). No real AWS creds are needed — the
backend storage is replaced with a mock.
"""
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage import StorageProvider, storage_provider


def _setup():
    owner = UserProfile.objects.create(cognito_sub="sub-signed", email="signed@test.com")
    project = Project.objects.create(owner=owner, prompt="signed url test")
    scene = Scene.objects.create(project=project, index=0)
    # Upload a file via InMemoryStorage so the field is non-empty
    scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)
    scene.refresh_from_db()
    return scene


class StorageProviderUrlTest(TestCase):
    """url() delegates to the selected backend's storage.url(name)."""

    def test_url_delegates_to_backend_storage(self):
        scene = _setup()

        mock_storage = MagicMock()
        mock_storage.url.return_value = (
            "https://bucket.s3.amazonaws.com/path?X-Amz-Expires=3600&sig=abc"
        )

        provider = StorageProvider()
        with patch.object(provider, "storage", mock_storage):
            url = provider.url(scene.media_path)

        mock_storage.url.assert_called_once_with(scene.media_path.name)
        self.assertIn("X-Amz-Expires=3600", url)

    def test_url_returns_none_for_empty_field(self):
        owner = UserProfile.objects.create(cognito_sub="sub-signed-empty", email="se@test.com")
        project = Project.objects.create(owner=owner, prompt="empty field")
        scene = Scene.objects.create(project=project, index=0)

        provider = StorageProvider()
        self.assertIsNone(provider.url(scene.media_path))


class FieldUrlApiTest(TestCase):
    """The module-level storage_provider facade returns a usable URL."""

    def test_returns_local_url_in_test_settings(self):
        scene = _setup()
        url = storage_provider.url(scene.media_path)
        self.assertIsNotNone(url)
        self.assertIsInstance(url, str)

    def test_returns_none_for_empty_field(self):
        owner = UserProfile.objects.create(cognito_sub="sub-fu-empty", email="fue@test.com")
        project = Project.objects.create(owner=owner, prompt="empty")
        scene = Scene.objects.create(project=project, index=0)
        self.assertIsNone(storage_provider.url(scene.media_path))
