"""Image provider interface.

To add a backend: create a module with an ImageProvider subclass and append an
instance to PROVIDERS in __init__.py. List order = auto-pick priority.
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.secure import SecureString


class ImageProvider(ABC):
    name: str = ""
    requires: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True when this backend is usable (credentials/deps present)."""

    @abstractmethod
    def generate(self, prompt: str, query: str | None = None,
                 negative: str | None = None,
                 api_key: "SecureString | None" = None,
                 model: str | None = None) -> bytes:
        """Return a 1920x1080 PNG as bytes, or raise to let the fallback
        chain try the next provider."""
