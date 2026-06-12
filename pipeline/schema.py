"""The shot plan — the contract every downstream stage consumes."""
from typing import List, Optional

from pydantic import BaseModel, Field


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
    scenes: List[Scene] = Field(description="8-15 scenes. Scene durations come from the voiceover audio.")
