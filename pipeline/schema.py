"""The shot plan — the contract every downstream stage consumes."""
import re
from typing import List, Optional

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str = Field(description="Short lowercase placeholder id, e.g. 'thief' or 'mom'.")
    description: str = Field(
        description="Full visual description: age, hair, face, every clothing item "
        "with its color, e.g. 'a mid-30s man with short black hair and stubble, wearing "
        "a black zip-up hoodie, dark blue jeans and white sneakers'."
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
    negative_prompt: Optional[str] = Field(
        default=None,
        description="Optional: things the image must NOT contain, e.g. 'beard, mustache'. "
        "Use for traits the model keeps adding; never phrase negatives in image_prompt.",
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
    scenes: List[Scene] = Field(description="8-15 scenes. Scene durations come from the voiceover audio.")

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
        """
        substituted = False
        for c in self.characters:
            desc = c.description.strip().rstrip(".")
            pattern = r"\{" + re.escape(c.name) + r"\}|\b" + re.escape(c.name) + r"\b"
            new = re.sub(pattern, desc, text, flags=re.IGNORECASE)
            if new != text:
                substituted = True
                text = new
        if substituted:
            # collapse double articles produced by "the {name}" -> "the a young boy ..."
            text = re.sub(r"\b(?:the|a|an) (a|an|the)\b", r"\1", text, flags=re.IGNORECASE)
        return text
