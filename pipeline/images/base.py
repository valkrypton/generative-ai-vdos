"""Image provider interface.

To add a backend: create a module with an ImageProvider subclass and append an
instance to PROVIDERS in __init__.py. List order = auto-pick priority.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class ImageProvider(ABC):
    name: str = ""
    cost_note: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True when this backend is usable (credentials/deps present)."""

    @abstractmethod
    def generate(self, prompt: str, path: Path, query: Optional[str] = None) -> None:
        """Write a 1920x1080 png to path, or raise to let the fallback chain try
        the next provider. query is the bare scene description without the
        style_prefix (search-based backends match better on it)."""
