"""Stage 2: one image per scene, via pluggable provider backends.

Adding a backend: write a module with an ImageProvider subclass (see base.py)
and append an instance to PROVIDERS below. List order = auto-pick priority.

Selection: an explicit backend name wins; otherwise the first available()
provider is used. If a provider fails on a scene (moderation block, no search
results, network error), the remaining available providers are tried in order,
ending at the always-available placeholder.
"""
from pathlib import Path
from typing import List, Optional, Tuple

from ..schema import ShotPlan
from .base import ImageProvider
from .flux import FluxProvider
from .gpt_image import GptImageProvider
from .pexels import PexelsProvider
from .placeholder import PlaceholderProvider
from .qwen_image import QwenImageProvider

PROVIDERS: List[ImageProvider] = [
    FluxProvider(),
    QwenImageProvider(),  # free quota — preferred over paid gpt-image-1
    GptImageProvider(),
    PexelsProvider(),
    PlaceholderProvider(),
]


def get_provider(name: Optional[str] = None) -> ImageProvider:
    if name:
        for p in PROVIDERS:
            if p.name == name:
                if not p.available():
                    raise RuntimeError(
                        f"image backend '{name}' is not configured (missing API key or package)")
                return p
        raise RuntimeError(
            f"unknown image backend '{name}' — choices: {', '.join(p.name for p in PROVIDERS)}")
    return next(p for p in PROVIDERS if p.available())


def generate_scene_image(
    plan: ShotPlan, index: int, out_dir: Path, primary: ImageProvider,
    fallback: bool = True,
) -> Tuple[Path, ImageProvider]:
    """Generate one scene's image. With fallback (auto-picked backend), failures
    fall through the remaining providers; an explicitly forced backend fails loudly."""
    scene = plan.scenes[index]
    path = out_dir / f"scene_{index:02d}.png"
    scene_prompt = plan.expand(scene.image_prompt)
    prompt = f"{plan.style_prefix}, {scene_prompt}"
    chain = [primary]
    if fallback:
        chain += [p for p in PROVIDERS if p is not primary and p.available()]
    last_error = None
    for provider in chain:
        try:
            provider.generate(prompt, path, query=scene_prompt, negative=scene.negative_prompt)
            return path, provider
        except Exception as e:
            last_error = e
            more = "; trying next" if provider is not chain[-1] else ""
            print(f"  images: scene {index + 1} via {provider.name} failed ({e}){more}")
    raise RuntimeError(f"image generation failed for scene {index + 1}: {last_error}")


def generate_images(plan: ShotPlan, out_dir: Path, backend: Optional[str] = None) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    primary = get_provider(backend)
    print(f"  images: backend = {primary.name}")
    if plan.characters:
        print("  images: character check (same description substituted in every scene):")
        for i, scene in enumerate(plan.scenes):
            chars = plan.characters_in(scene.image_prompt)
            print(f"    scene {i}: {', '.join(chars) if chars else '-'}")
    paths = []
    for i in range(len(plan.scenes)):
        path, used = generate_scene_image(plan, i, out_dir, primary, fallback=backend is None)
        note = "" if used is primary else f" (fell back to {used.name})"
        print(f"  images: scene {i + 1}/{len(plan.scenes)}{note}")
        paths.append(path)
    return paths
