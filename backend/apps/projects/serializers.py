from rest_framework import serializers
from .models import Project, Scene, JobLog


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


class ProjectSerializer(serializers.ModelSerializer):
    scenes = SceneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "title", "prompt", "status", "shot_plan",
            "image_backend", "animate", "narrator_voice", "music",
            "error", "stale", "scenes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "error", "stale", "created_at", "updated_at"]


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["prompt", "title", "image_backend", "animate", "narrator_voice", "music"]
