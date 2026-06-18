from django.db import models

TRANSITIONS = {
    "DRAFT": {"PLANNING"},
    "PLANNING": {"REVIEW", "FAILED"},
    "REVIEW": {"PLANNING", "GENERATING"},
    "GENERATING": {"DONE", "FAILED"},
    "FAILED": {"GENERATING"},
    "DONE": set(),
}


class Status(models.TextChoices):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    REVIEW = "REVIEW"
    GENERATING = "GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class ImageStatus(models.TextChoices):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class Level(models.TextChoices):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Stage(models.TextChoices):
    PLAN = "plan"
    IMAGES = "images"
    VOICE = "voice"
    VIDEO = "video"
    ASSEMBLE = "assemble"


class MusicMood(models.TextChoices):
    CALM = "calm"
    UPBEAT = "upbeat"
    DRAMATIC = "dramatic"
    MYSTERIOUS = "mysterious"
    INSPIRING = "inspiring"


class Capability(models.TextChoices):
    PLAN  = "plan",  "Shot Plan (LLM)"
    IMAGE = "image", "Image Generation"
    VIDEO = "video", "Video Animation"


class StylePreset(models.TextChoices):
    CINEMATIC   = "cinematic",   "Cinematic"
    ANIME       = "anime",       "Anime"
    WATERCOLOR  = "watercolor",  "Watercolor"
    DOCUMENTARY = "documentary", "Documentary"
    STORYBOOK   = "storybook",   "Storybook"
    NOIR        = "noir",        "Noir"
    RETRO_PIXEL = "retro-pixel", "Retro Pixel"


class NarratorVoice(models.TextChoices):
    ANDREW = "en-US-AndrewNeural", "Andrew (US Male)"
    RYAN = "en-US-RyanNeural", "Ryan (GB Male)"
    AVA = "en-US-AvaNeural", "Ava (US Female)"
