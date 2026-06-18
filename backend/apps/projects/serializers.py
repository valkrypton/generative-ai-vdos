from rest_framework import serializers
from .models import LLMModel, Project, Scene, JobLog


class SceneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scene
        fields = ["id", "index", "media_path", "image_status", "image_provider", "created_at", "updated_at"]
        read_only_fields = ["id", "index", "media_path", "image_status", "image_provider", "created_at", "updated_at"]


class JobLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobLog
        fields = ["id", "stage", "level", "message", "created_at"]
        read_only_fields = ["id", "stage", "level", "message", "created_at"]


class LLMModelSerializer(serializers.ModelSerializer):
    provider = serializers.CharField(source="provider.code", read_only=True)

    class Meta:
        model = LLMModel
        fields = ["id", "model_id", "display_name", "provider", "capability", "is_free", "is_default"]
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    scenes = SceneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "title", "prompt", "status", "shot_plan",
            "plan_model", "image_model", "video_model",
            "style", "animate", "narrator_voice", "music",
            "error", "stale", "scenes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "shot_plan", "error", "stale", "created_at", "updated_at"]


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["prompt", "title", "plan_model", "image_model", "video_model", "style", "animate", "narrator_voice", "music"]
