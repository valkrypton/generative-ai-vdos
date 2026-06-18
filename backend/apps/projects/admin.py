from django.contrib import admin

from .models import JobLog, LLMModel, Project, Scene


@admin.register(LLMModel)
class LLMModelAdmin(admin.ModelAdmin):
    list_display = ["display_name", "provider", "capability", "model_id", "is_free", "is_default", "is_active"]
    list_select_related = ["provider"]
    list_filter = ["capability", "is_active", "is_free", "provider"]
    search_fields = ["display_name", "model_id"]


class SceneInline(admin.TabularInline):
    model = Scene
    extra = 0
    readonly_fields = ["index", "narration", "media_prompt", "image_status", "image_provider", "media_path"]
    fields = readonly_fields


class JobLogInline(admin.TabularInline):
    model = JobLog
    extra = 0
    readonly_fields = ["stage", "level", "message", "created_at"]
    fields = readonly_fields


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "owner", "status", "style", "plan_model", "image_model", "created_at"]
    list_select_related = ["owner", "plan_model", "plan_model__provider", "image_model", "image_model__provider"]
    list_filter = ["status"]
    search_fields = ["title", "prompt", "owner__email"]
    readonly_fields = ["id", "status", "shot_plan", "error", "stale", "created_at", "updated_at"]
    inlines = [SceneInline, JobLogInline]
