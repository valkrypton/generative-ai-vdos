from abc import ABC, abstractmethod
from pathlib import Path

from django.db.models.fields.files import FieldFile


class BaseStorageProvider(ABC):
    """
    Abstract interface for file-storage operations on Django FileFields.

    Concrete subclasses encapsulate backend-specific behaviour (signed URL
    expiry, overwrite rules, etc.) while the application code stays the same
    regardless of the configured storage backend.
    """

    @abstractmethod
    def upload(self, field_file: FieldFile, local_path: Path, *, save: bool = True) -> None:
        """
        Open local_path and write its contents to field_file via the storage
        backend. When save=True (default) the model row is updated immediately.
        Pass save=False to batch multiple field writes before a single .save().
        """

    @abstractmethod
    def url(self, field_file: FieldFile) -> str | None:
        """
        Return an access URL for field_file, or None if the field is empty.
        Implementations must handle empty fields gracefully.
        """
