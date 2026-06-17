import uuid
from django.db import models
from apps.core.models import TimestampMixin
from apps.projects.constants import NarratorVoice, MusicMood, Stage, Level, ImageStatus, _TRANSITIONS, Status
from apps.accounts.models import UserProfile


class Project(TimestampMixin):
    Status = Status
    ImageStatus = ImageStatus

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner          = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="projects", db_index=True
    )
    prompt         = models.TextField()
    title          = models.CharField(max_length=200, blank=True, default="")
    status         = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    shot_plan      = models.JSONField(null=True, blank=True)
    image_backend  = models.CharField(max_length=50, blank=True, default="")
    animate        = models.BooleanField(default=False)
    narrator_voice = models.CharField(
        max_length=100, choices=NarratorVoice, blank=True, default=NarratorVoice.ANDREW
    )
    music          = models.CharField(
        max_length=200, choices=MusicMood ,blank=True, default=MusicMood.CALM
    )
    error          = models.TextField(blank=True, default="")
    stale          = models.BooleanField(default=False)

    def transition_status(self, new_status):
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition Project from {self.status!r} to {new_status!r}."
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return f"Project({self.id}, {self.status})"


class Scene(TimestampMixin):
    ImageStatus = ImageStatus

    project        = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="scenes"
    )
    index          = models.IntegerField()
    narration      = models.TextField()
    media_prompt         = models.TextField()
    on_screen_text = models.CharField(max_length=256,blank=True, default="")
    negative_prompt = models.TextField(max_length=256, blank=True, default="")
    animate        = models.BooleanField(default=False)
    media_path     = models.CharField(max_length=500, blank=True, default="")
    image_status   = models.CharField(
        max_length=20, choices=ImageStatus.choices, default=ImageStatus.PENDING
    )
    image_provider = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]


class JobLog(TimestampMixin):
    project    = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="logs")
    stage      = models.CharField(max_length=10, choices=Stage.choices)
    level      = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    message    = models.TextField()

    class Meta:
        ordering = ["created_at"]
