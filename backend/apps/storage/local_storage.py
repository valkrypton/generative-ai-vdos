from pathlib import Path

from django.core.files import File
from django.db.models.fields.files import FieldFile

from apps.storage.base_storage import BaseStorageProvider



class LocalStorageProvider(BaseStorageProvider):
    """
    Wraps Django's FileSystemStorage (and InMemoryStorage in tests).
    URL generation returns a plain /media/… path served by Django in dev.
    """

    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        with local_path.open("rb") as fh:
            field_file.save(local_path.name, File(fh), save=save)

    def url(self, field_file: FieldFile) -> str | None:
        return field_file.url if field_file else None