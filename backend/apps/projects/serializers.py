import os

from django.db.models import F, Q
from rest_framework import serializers

from apps.core.models import Provider
from apps.core.moderation.drf import ModeratedFieldsMixin
from apps.storage import storage_provider
from apps.projects.models import JobLog, LLMModel, Project, Scene


def _absolute_media_url(url: str, request) -> str:
    if not url:
        return ""
    # S3 presigned URLs — return as-is.
    if url.startswith(("http://", "https://")):
        return url
    # Local FileSystemStorage paths (/media/…) — keep relative so the browser
    # resolves them against the public webapp origin. SSR fetches Django via
    # 127.0.0.1:8000, so request.build_absolute_uri() would embed localhost.
    if url.startswith("/"):
        return url
    if request is not None:
        return request.build_absolute_uri(f"/{url.lstrip('/')}")
    origin = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{origin}/{url.lstrip('/')}"


class ScopedModelSlugField(serializers.SlugRelatedField):
    """Resolve an LLMModel by ``model_id``, scoped to the requesting user.

    Two safety properties the plain SlugRelatedField lacked:
    - **Scoping**: only global rows (owner NULL) and the user's own custom rows
      are selectable, so a user can't attach another user's private model.
    - **No 500 on duplicates**: ``model_id`` is unique only per
      (provider, capability, owner), so two active rows can share one. The base
      field's ``.get()`` would raise ``MultipleObjectsReturned``; we order
      global-first then lowest id and take ``.first()`` for a deterministic pick.
    """

    def __init__(self, capability, **kwargs):
        self.capability = capability
        kwargs.setdefault("slug_field", "model_id")
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        # queryset is computed per-request in get_queryset(); a static one here
        # would ignore the user scope.
        kwargs["queryset"] = LLMModel.objects.none()
        super().__init__(**kwargs)

    def get_queryset(self):
        qs = LLMModel.objects.filter(capability=self.capability, is_active=True)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            return qs.filter(Q(owner__isnull=True) | Q(owner=request.user))
        return qs.filter(owner__isnull=True)

    def to_internal_value(self, data):
        try:
            obj = (
                self.get_queryset()
                .filter(**{self.slug_field: data})
                .order_by(F("owner_id").asc(nulls_first=True), "id")
                .first()
            )
        except (TypeError, ValueError):
            self.fail("invalid")
        if obj is None:
            self.fail("does_not_exist", slug_name=self.slug_field, value=str(data))
        return obj


def _model_slug(capability):
    return ScopedModelSlugField(capability)


class SceneSerializer(serializers.ModelSerializer):
    media_path = serializers.SerializerMethodField()
    audio_path = serializers.SerializerMethodField()

    class Meta:
        model = Scene
        fields = [
            "id", "index", "narration", "media_prompt", "animate", "voice",
            "on_screen_text", "negative_prompt",
            "preview_url",
            "media_path", "audio_path", "media_status", "voice_status", "media_provider",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "index", "preview_url", "media_status", "voice_status",
            "media_provider", "created_at", "updated_at",
        ]

    def get_media_path(self, obj) -> str:
        return _absolute_media_url(
            storage_provider.url(obj.media_path) or "",
            self.context.get("request"),
        )

    def get_audio_path(self, obj) -> str:
        return _absolute_media_url(
            storage_provider.url(obj.audio_path) or "",
            self.context.get("request"),
        )


class SceneUpdateSerializer(ModeratedFieldsMixin, serializers.ModelSerializer):
    moderated_fields = ("narration", "media_prompt", "on_screen_text", "negative_prompt")

    class Meta:
        model = Scene
        fields = ["narration", "media_prompt", "animate", "on_screen_text", "negative_prompt"]


class JobLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobLog
        fields = ["id", "stage", "level", "message", "created_at"]
        read_only_fields = fields


class LLMModelSerializer(serializers.ModelSerializer):
    provider = serializers.PrimaryKeyRelatedField(
        queryset=Provider.objects.filter(is_active=True),
    )
    owned = serializers.SerializerMethodField()

    class Meta:
        model = LLMModel
        fields = [
            "id", "model_id", "display_name", "provider",
            "capability", "is_free", "is_default", "owned",
        ]
        read_only_fields = ["id", "is_free", "is_default", "owned"]

    def get_owned(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and obj.owner_id == request.user.id)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["provider"] = instance.provider.code
        return rep


class ProjectSerializer(ModeratedFieldsMixin, serializers.ModelSerializer):
    moderated_fields = ("prompt", "title")
    scenes = SceneSerializer(many=True, read_only=True)
    plan_model = _model_slug("plan")
    image_model = _model_slug("image")
    video_model = _model_slug("video")

    class Meta:
        model = Project
        fields = [
            "id", "title", "prompt", "status", "shot_plan",
            "plan_model", "image_model", "video_model",
            "style", "animate", "narrator_voice", "music",
            "error", "stale", "scenes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "error", "stale",
            "created_at", "updated_at",
        ]


class ProjectCreateSerializer(ModeratedFieldsMixin, serializers.ModelSerializer):
    moderated_fields = ("prompt", "title")
    plan_model = _model_slug("plan")
    image_model = _model_slug("image")
    video_model = _model_slug("video")

    class Meta:
        model = Project
        fields = [
            "prompt", "title", "plan_model", "image_model", "video_model",
            "style", "animate", "narrator_voice", "music",
        ]
