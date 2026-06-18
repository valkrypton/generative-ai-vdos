from django.utils.functional import SimpleLazyObject

from apps.storage.local_storage import LocalStorageProvider
from apps.storage.s3_storage import S3StorageProvider


def _get_provider():
    """
    Factory that returns the provider matching the current default storage
    backend. Detects S3Boto3Storage at runtime; falls back to LocalStorageProvider
    for FileSystemStorage and InMemoryStorage (dev + test).
    """
    from django.core.files.storage import default_storage
    try:
        from storages.backends.s3boto3 import S3Boto3Storage
        if isinstance(default_storage, S3Boto3Storage):
            expire = getattr(default_storage, "querystring_expire", 3600)
            return S3StorageProvider(expire=expire)
    except ImportError:
        pass
    return LocalStorageProvider()


# Global storage provider — lazily instantiated on first access so it is safe
# to import at module level before Django's app registry is fully loaded.
# Mirrors how Django exposes django.core.files.storage.default_storage.
#
# Usage from any Django app:
#   from apps.storage import storage_provider
#   storage_provider.upload(scene.media_path, disk_path)
#   storage_provider.url(scene.media_path)
storage_provider = SimpleLazyObject(_get_provider)
