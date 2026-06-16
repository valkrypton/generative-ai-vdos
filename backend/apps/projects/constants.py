from django.db import models

_TRANSITIONS = {
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


class NarratorVoice(models.TextChoices):
    ANDREW = "en-US-AndrewNeural", "Andrew (US Male)"
    RYAN = "en-US-RyanNeural", "Ryan (GB Male)"
    AVA = "en-US-AvaNeural", "Ava (US Female)"
