"""
Verifies signed-URL behavior by monkey-patching _get_provider() to
return an S3StorageProvider backed by a mock, without requiring real AWS creds.
"""
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.storage.s3_storage import S3StorageProvider
from apps.storage import storage_provider


def _setup():
    owner = UserProfile.objects.create(cognito_sub="sub-signed", email="signed@test.com")
    project = Project.objects.create(owner=owner, prompt="signed url test")
    scene = Scene.objects.create(project=project, index=0)
    # Upload a file via InMemoryStorage so the field is non-empty
    scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)
    scene.refresh_from_db()
    return scene


class S3StorageProviderUrlTest(TestCase):
    """S3StorageProvider.url() calls storage.url(name, expire=...) not field_file.url."""

    def test_url_calls_storage_url_with_expire(self):
        scene = _setup()

        mock_storage = MagicMock()
        mock_storage.url.return_value = "https://bucket.s3.amazonaws.com/path?X-Amz-Expires=3600&sig=abc"

        provider = S3StorageProvider(expire=3600)

        # Patch the field's storage attribute so provider hits our mock
        with patch.object(scene.media_path, "storage", mock_storage):
            url = provider.url(scene.media_path)

        mock_storage.url.assert_called_once_with(scene.media_path.name, expire=3600)
        self.assertIn("X-Amz-Expires=3600", url)

    def test_url_returns_none_for_empty_field(self):
        owner = UserProfile.objects.create(cognito_sub="sub-signed-empty", email="se@test.com")
        project = Project.objects.create(owner=owner, prompt="empty field")
        scene = Scene.objects.create(project=project, index=0)

        provider = S3StorageProvider(expire=3600)
        result = provider.url(scene.media_path)
        self.assertIsNone(result)

    def test_custom_expire_forwarded_to_storage(self):
        scene = _setup()

        mock_storage = MagicMock()
        mock_storage.url.return_value = "https://bucket.s3.amazonaws.com/path?X-Amz-Expires=1800"

        provider = S3StorageProvider(expire=1800)
        with patch.object(scene.media_path, "storage", mock_storage):
            provider.url(scene.media_path)

        _, kwargs = mock_storage.url.call_args
        self.assertEqual(kwargs["expire"], 1800)


class GetStorageProviderS3DetectionTest(TestCase):
    """_get_provider() returns the correct subclass based on the active backend."""

    def test_returns_local_provider_in_test_settings(self):
        from apps.storage import _get_provider
        from apps.storage.local_storage import LocalStorageProvider
        self.assertIsInstance(_get_provider(), LocalStorageProvider)

    def test_returns_s3_provider_when_default_storage_is_s3(self):
        from storages.backends.s3boto3 import S3Boto3Storage
        from apps.storage import _get_provider
        mock_s3 = MagicMock(spec=S3Boto3Storage)
        mock_s3.querystring_expire = 1800

        # default_storage is imported inside _get_provider() — patch at the source module.
        with patch("django.core.files.storage.default_storage", mock_s3):
            provider = _get_provider()

        self.assertIsInstance(provider, S3StorageProvider)
        self.assertEqual(provider._expire, 1800)


class FieldUrlApiTest(TestCase):
    """storage_provider.url() facade dispatches to the active provider."""

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
