"""Curated style presets for visual consistency across videos."""

from __future__ import annotations

import sys

PRESETS: dict[str, dict[str, str | None]] = {
    "cinematic": {
        "style_prefix": (
            "cinematic photo, muted colors, shallow depth of field, "
            "anamorphic lens flare, film grain"
        ),
        "global_negative": (
            "cartoon, anime, drawing, painting, oversaturated, "
            "text, watermark, blurry, extra limbs"
        ),
        "music_mood": "dramatic",
    },
    "anime": {
        "style_prefix": (
            "anime illustration, vibrant cel-shading, bold outlines, "
            "detailed backgrounds, studio ghibli inspired"
        ),
        "global_negative": (
            "photorealistic, photo, 3d render, text, watermark, "
            "blurry, extra limbs, bad anatomy"
        ),
        "music_mood": "upbeat",
    },
    "watercolor": {
        "style_prefix": (
            "watercolor painting, soft washes, visible brush strokes, "
            "muted pastel palette, textured paper"
        ),
        "global_negative": (
            "photo, photorealistic, sharp lines, digital art, "
            "text, watermark, blurry"
        ),
        "music_mood": "calm",
    },
    "documentary": {
        "style_prefix": (
            "photojournalistic photo, natural lighting, candid composition, "
            "neutral color grade, 35mm lens"
        ),
        "global_negative": (
            "cartoon, painting, stylized, text, watermark, "
            "blurry, extra limbs, oversaturated"
        ),
        "music_mood": "inspiring",
    },
    "storybook": {
        "style_prefix": (
            "children's storybook illustration, warm soft colors, "
            "whimsical details, hand-drawn feel, gentle lighting"
        ),
        "global_negative": (
            "photo, photorealistic, dark, scary, violent, "
            "text, watermark, blurry"
        ),
        "music_mood": "calm",
    },
    "noir": {
        "style_prefix": (
            "film noir, high contrast black and white, dramatic shadows, "
            "venetian blind lighting, rain-slicked streets"
        ),
        "global_negative": (
            "color, colorful, bright, cartoon, anime, "
            "text, watermark, blurry, extra limbs"
        ),
        "music_mood": "mysterious",
    },
    "retro-pixel": {
        "style_prefix": (
            "16-bit pixel art, retro game aesthetic, limited color palette, "
            "dithering, CRT scanlines"
        ),
        "global_negative": (
            "photo, photorealistic, smooth gradients, 3d render, "
            "text, watermark, blurry"
        ),
        "music_mood": "upbeat",
    },
}


def resolve_style(raw: str | None) -> dict[str, str | None] | None:
    """Resolve a CLI/env style value into a preset dict (or None)."""
    if raw is None:
        return None

    if raw == "list":
        _list_presets()
        sys.exit(0)

    if raw.startswith("custom:"):
        return {
            "style_prefix": raw.removeprefix("custom:").strip(),
            "global_negative": None,
            "music_mood": None,
        }

    key = raw.lower()
    if key in PRESETS:
        return PRESETS[key]

    raise ValueError(
        f"Unknown style '{raw}'. Available: {', '.join(PRESETS)}"
    )


def _list_presets() -> None:
    for name, preset in PRESETS.items():
        print(f"  {name:<14} {preset['style_prefix']}")


def inject_style_instruction(preset: dict[str, str | None]) -> str:
    """Build an LLM instruction block that constrains style fields."""
    lines = [
        "STYLE CONSTRAINT (mandatory — do not override):",
        f'- style_prefix must be exactly: "{preset["style_prefix"]}"',
    ]
    if preset.get("global_negative"):
        lines.append(
            f'- global_negative must be exactly: "{preset["global_negative"]}"'
        )
    if preset.get("music_mood"):
        lines.append(f'- music_mood must be exactly: "{preset["music_mood"]}"')
    lines.append(
        "\nREMINDER: Any visual element (object, person, animal, flag, vehicle) "
        "that appears in more than one scene MUST have a character entry with a "
        "{placeholder} in every image_prompt where it appears. This includes "
        "key props like food, treasures, or landmarks — not just people."
    )
    return "\n".join(lines)
