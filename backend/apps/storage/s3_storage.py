from pathlib import Path

from django.core.files import File
from django.db.models.fields.files import FieldFile

from apps.storage.base_storage import BaseStorageProvider

class S3StorageProvider(BaseStorageProvider):
    """
    Wraps django-storages S3Boto3Storage.
    Generates pre-signed URLs with a configurable expiry window so that
    private S3 objects can be accessed temporarily by authenticated users.
    """

    def __init__(self, expire: int = 3600):
        self._expire = expire

    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        with local_path.open("rb") as fh:
            field_file.save(local_path.name, File(fh), save=save)

    def url(self, field_file: FieldFile) -> str | None:
        if not field_file:
            return None
        # S3Boto3Storage.url() accepts an expire kwarg; bypass FieldFile.url
        # so we can pass the per-call expiry rather than relying solely on
        # the global querystring_expire setting.
        return field_file.storage.url(field_file.name, expire=self._expire)