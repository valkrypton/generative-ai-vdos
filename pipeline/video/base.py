"""Video provider interface — image-to-video animation of scene stills.

To add a backend: create a module with a VideoProvider subclass and append an
instance to PROVIDERS in __init__.py. List order = auto-pick priority.

Providers that run as async server-side tasks should also implement
submit()/poll()/download() — animate_scenes() then batches all scenes
concurrently instead of waiting on each clip in turn.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from pipeline.secure import SecureString


class VideoProvider(ABC):
    name: str = ""

    @abstractmethod
    def available(self) -> bool:
        """True when this backend is usable (credentials/deps present)."""

    @abstractmethod
    def generate(self, prompt: str, image_path: Path, out_path: Path,
                 api_key: "SecureString | None" = None) -> None:
        """Animate the still at image_path into a short mp4 at out_path."""

    # Optional async-task protocol (see module docstring):
    # submit(prompt, image_path) -> task_id: str
    # poll(task_id) -> Optional[str]   (video URL when done, None while running, raise on failure)
    # download(url, out_path) -> None
