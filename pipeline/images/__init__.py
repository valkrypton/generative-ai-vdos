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
    QwenImageProvider(),  # free — always first; also does reference-image editing (consistent faces)
    FluxProvider(),       # free tier only — costs money after quota
    PexelsProvider(),
    PlaceholderProvider(),
    GptImageProvider(),   # paid — never auto-selected, use --backend gpt-image-1 explicitly
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


def character_refs(plan: ShotPlan, provider: ImageProvider, out_dir: Path) -> dict:
    """Render one clean reference portrait per character (once) so single-character
    scenes can be edited from them for a consistent face/clothing. Only meaningful
    for providers that can edit from a reference (qwen-image, gpt-image-1); returns
    {} otherwise. A character whose portrait fails is simply omitted — its scenes
    fall back to text-to-image."""
    if not (plan.characters and hasattr(provider, "edit")):
        return {}
    ref_dir = out_dir / "refs"
    ref_dir.mkdir(parents=True, exist_ok=True)
    refs = {}
    print("  images: building character reference portraits (for face consistency)")
    for c in plan.characters:
        p = ref_dir / f"{c.name}.png"
        if not p.is_file():
            prompt = (f"{plan.style_prefix}, a character reference portrait of "
                      f"{c.description.strip().rstrip('.')}, neutral standing pose, "
                      f"plain neutral background, even lighting, full head and body visible")
            try:
                provider.generate(prompt, p, negative=c.negative)
            except Exception as e:
                print(f"    ref {c.name}: failed ({e}) — scenes will text-to-image instead")
                continue
        refs[c.name] = p
    return refs


def generate_scene_image(
    plan: ShotPlan, index: int, out_dir: Path, primary: ImageProvider,
    fallback: bool = True, char_refs: Optional[dict] = None,
) -> Tuple[Path, ImageProvider]:
    """Generate one scene's image. With fallback (auto-picked backend), failures
    fall through the remaining providers; an explicitly forced backend fails loudly."""
    scene = plan.scenes[index]
    path = out_dir / f"scene_{index:02d}.png"
    scene_prompt = plan.expand(scene.image_prompt)
    prompt = f"{plan.style_prefix}, {scene_prompt}"

    # Reference-image consistency: for a scene with exactly ONE character, edit
    # from that character's reference portrait so the face/clothing stays the same
    # scene to scene. (qwen-image-edit takes a single reference, so multi-character
    # scenes can't be locked this way — they fall through to text-to-image.)
    if char_refs and not scene.reference_image and hasattr(primary, "edit"):
        named = [n for n in plan.characters_in(scene.image_prompt) if n in char_refs]
        if len(named) == 1:
            edit_prompt = (prompt + " Keep the person's face, hair and clothing "
                           "identical to the reference image.")
            try:
                primary.edit(edit_prompt, char_refs[named[0]], path)
                return path, primary
            except Exception as e:
                print(f"  images: scene {index + 1} reference edit failed ({e}); "
                      "falling back to text-to-image")

    if scene.reference_image:
        ref = Path(scene.reference_image)
        if not ref.is_file():
            raise RuntimeError(f"scene {index + 1}: reference_image not found: {ref}")
        editor = primary if hasattr(primary, "edit") else next(
            (p for p in PROVIDERS if hasattr(p, "edit") and p.available()), None)
        if editor is None:
            raise RuntimeError("reference_image needs a backend with edit support "
                               "(gpt-image-1 — set OPENAI_API_KEY)")
        editor.edit(prompt, ref, path)
        return path, editor

    # Merge: global plan negative + per-character negatives + scene negative
    char_negatives = [
        c.negative for c in plan.characters
        if c.negative and c.name in plan.characters_in(scene.image_prompt)
    ]
    merged_negative = ", ".join(filter(None, [
        plan.global_negative,
        *char_negatives,
        scene.negative_prompt,
    ])) or None

    chain = [primary]
    if fallback:
        chain += [p for p in PROVIDERS if p is not primary and p.available()]
    last_error = None
    for provider in chain:
        try:
            provider.generate(prompt, path, query=scene_prompt, negative=merged_negative)
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
    refs = character_refs(plan, primary, out_dir)
    paths = []
    for i in range(len(plan.scenes)):
        path, used = generate_scene_image(plan, i, out_dir, primary,
                                          fallback=backend is None, char_refs=refs)
        note = "" if used is primary else f" (fell back to {used.name})"
        print(f"  images: scene {i + 1}/{len(plan.scenes)}{note}")
        paths.append(path)
    return paths
