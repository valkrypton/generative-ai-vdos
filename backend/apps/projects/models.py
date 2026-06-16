import uuid
from django.db import models
from apps.users.models import UserProfile

_TRANSITIONS = {
    "DRAFT":      {"PLANNING"},
    "PLANNING":   {"REVIEW", "FAILED"},
    "REVIEW":     {"GENERATING"},
    "GENERATING": {"DONE", "FAILED"},
    "FAILED":     {"GENERATING"},
    "DONE":       set(),
}


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT      = "DRAFT"
        PLANNING   = "PLANNING"
        REVIEW     = "REVIEW"
        GENERATING = "GENERATING"
        DONE       = "DONE"
        FAILED     = "FAILED"

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
    narrator_voice = models.CharField(max_length=100, blank=True, default="")
    music          = models.CharField(max_length=200, blank=True, default="")
    error          = models.TextField(blank=True, default="")
    stale          = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

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


class Scene(models.Model):
    class ImageStatus(models.TextChoices):
        PENDING = "PENDING"
        RUNNING = "RUNNING"
        DONE    = "DONE"
        FAILED  = "FAILED"

    project        = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="scenes"
    )
    index          = models.IntegerField()
    image_path     = models.CharField(max_length=500, blank=True, default="")
    image_status   = models.CharField(
        max_length=20, choices=ImageStatus.choices, default=ImageStatus.PENDING
    )
    image_provider = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        unique_together = ("project", "index")
        ordering = ["index"]


class JobLog(models.Model):
    class Level(models.TextChoices):
        INFO  = "info"
        WARN  = "warn"
        ERROR = "error"

    project    = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="logs")
    stage      = models.CharField(max_length=50)
    level      = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    message    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
