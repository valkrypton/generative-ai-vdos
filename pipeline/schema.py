"""The shot plan — the contract every downstream stage consumes."""
import re
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

MAX_ANIMATED_SCENES = 2  # hard cap — animating costs DashScope credit


class Character(BaseModel):
    name: str = Field(description="Short lowercase placeholder id, e.g. 'thief' or 'mom'.")
    description: str = Field(
        description="Full visual description: age, hair, face, every clothing item "
        "with its color, e.g. 'a mid-30s man with short black hair and stubble, wearing "
        "a black zip-up hoodie, dark blue jeans and white sneakers'."
    )
    negative: Optional[str] = Field(
        default=None,
        description="Traits this character must NEVER have in any scene. Merged automatically "
        "into the negative_prompt of every scene they appear in. Use for traits the image "
        "model keeps adding: e.g. 'hair, beard' for a bald character; "
        "'dark hair, black hair' for a white-haired character.",
    )


class Scene(BaseModel):
    narration: str = Field(description="Voiceover text for this scene, 1-3 sentences.")
    image_prompt: str = Field(
        description="Visual description for image generation. Concrete and specific; "
        "no text rendering requests. The global style_prefix is prepended automatically."
    )
    on_screen_text: Optional[str] = Field(
        default=None, description="Optional short overlay text (max ~6 words)."
    )
    voice: Optional[str] = Field(
        default=None,
        description="Optional edge-tts voice for this scene only (e.g. for dialogue: "
        "'ur-PK-UzmaNeural'). Default: the run-wide narrator voice.",
    )
    motion: Optional[str] = Field(
        default=None,
        description="Optional motion description for the animate stage, e.g. "
        "'the girl is talking, lips moving as she speaks, gesturing with her hands'. "
        "Default: gentle cinematic motion derived from image_prompt.",
    )
    animate: bool = Field(
        default=False,
        description="True only when real motion is essential — flags waving, characters "
        "fighting/dancing/running, animals in action, flowing water, crowd movement. "
        "False for text cards, still portraits, and wide shots where Ken Burns is enough. "
        "Animating costs DashScope credit; be selective.",
    )
    negative_prompt: Optional[str] = Field(
        default=None,
        description="Optional: things the image must NOT contain, e.g. 'beard, mustache'. "
        "Use for traits the model keeps adding; never phrase negatives in image_prompt.",
    )
    reference_image: Optional[str] = Field(
        default=None,
        description="Optional path to a local photo to build this scene on (a real "
        "building, person, product). The image model edits/composes from it instead of "
        "generating from scratch. Needs a backend with edit support (gpt-image-1).",
    )


class ShotPlan(BaseModel):
    title: str = Field(description="YouTube title, under 70 characters, curiosity-driven.")
    description: str = Field(description="YouTube description, 2-4 sentences plus hashtags.")
    tags: List[str] = Field(description="10-15 YouTube tags.")
    music_mood: str = Field(
        description="One word mood for background music: calm, upbeat, dramatic, mysterious, or inspiring."
    )
    style_prefix: str = Field(
        description="Global image style prepended to every scene's image prompt, "
        "e.g. 'cinematic photo, muted colors, shallow depth of field'."
    )
    characters: List[Character] = Field(
        default_factory=list,
        description="Recurring characters. In image_prompt and motion, reference them "
        "ONLY by placeholder, e.g. {thief} — the pipeline substitutes the full "
        "description into every scene, guaranteeing a consistent look.",
    )
    global_negative: Optional[str] = Field(
        default=None,
        description="Negative prompt applied to EVERY scene in the video regardless of "
        "which characters appear. Use for video-wide rules: e.g. "
        "'changing hairstyle, inconsistent clothing, different face, text, watermark, "
        "extra limbs, blurry'. Merged with per-character and per-scene negatives automatically.",
    )
    scenes: List[Scene] = Field(description="8-15 scenes. Scene durations come from the voiceover audio.")

    @model_validator(mode="after")
    def cap_animated_scenes(self) -> "ShotPlan":
        animated = [i for i, s in enumerate(self.scenes) if s.animate]
        if len(animated) > MAX_ANIMATED_SCENES:
            # Force the extra ones off — keep only the first MAX_ANIMATED_SCENES
            for i in animated[MAX_ANIMATED_SCENES:]:
                self.scenes[i].animate = False
        return self

    def characters_in(self, text: str) -> List[str]:
        """Names of characters referenced in text (via {placeholder} or bare name)."""
        found = []
        for c in self.characters:
            pattern = r"\{" + re.escape(c.name) + r"\}|\b" + re.escape(c.name) + r"\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                found.append(c.name)
        return found

    def expand(self, text: str) -> str:
        """Replace character references with their full descriptions.

        Matches both {name} placeholders and bare names (word-boundary,
        case-insensitive) — LLMs frequently forget the braces.

        A character mentioned more than once in the same text gets its full
        description on the FIRST mention only; later mentions collapse to a
        short reference (e.g. "the eldest daughter"). Repeating a full
        description bloats the prompt and can make the image model render the
        same person twice.
        """
        substituted = False
        for c in self.characters:
            desc = c.description.strip().rstrip(".")
            short = "the " + c.name.replace("_", " ")
            pattern = r"\{" + re.escape(c.name) + r"\}|\b" + re.escape(c.name) + r"\b"

            # Single pass over the ORIGINAL text: first match -> full description,
            # any further ones -> short ref. One pass (not two) so the substituted
            # description is never re-scanned — important when a description
            # contains the character's own name (e.g. "a reddish-brown octopus").
            seen = {"n": 0}

            def repl(m, desc=desc, short=short, seen=seen):
                seen["n"] += 1
                return desc if seen["n"] == 1 else short

            new, n = re.subn(pattern, repl, text, flags=re.IGNORECASE)
            if n:
                substituted = True
                text = new
        if substituted:
            # collapse double articles produced by "the {name}" -> "the a young boy ..."
            text = re.sub(r"\b(?:the|a|an) (a|an|the)\b", r"\1", text, flags=re.IGNORECASE)
        # always collapse double spaces — can appear after placeholder substitution
        text = re.sub(r" {2,}", " ", text).strip()
        return text
