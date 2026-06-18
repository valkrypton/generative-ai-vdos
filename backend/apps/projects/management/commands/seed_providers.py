from django.core.management.base import BaseCommand

from apps.core.models import Provider
from apps.projects.constants import Capability
from apps.projects.models import LLMModel

PROVIDERS = [
    {"code": "openai",    "name": "OpenAI"},
    {"code": "anthropic", "name": "Anthropic"},
    {"code": "google",    "name": "Google"},
    {"code": "dashscope", "name": "DashScope (Alibaba)"},
    {"code": "litellm",   "name": "LiteLLM"},
    {"code": "replicate", "name": "Replicate"},
    {"code": "pexels",    "name": "Pexels"},
]

MODELS = [
    # Plan models
    {"provider": "google",    "capability": Capability.PLAN,  "model_id": "gemini-3.1-flash-lite", "display_name": "Gemini Flash Lite (free)", "is_free": True,  "is_default": True},
    {"provider": "google",    "capability": Capability.PLAN,  "model_id": "gemini-2.5-flash",      "display_name": "Gemini Flash",             "is_free": False, "is_default": False},
    {"provider": "openai",    "capability": Capability.PLAN,  "model_id": "gpt-4o-mini",           "display_name": "GPT-4o Mini",              "is_free": False, "is_default": False},
    {"provider": "anthropic", "capability": Capability.PLAN,  "model_id": "claude-haiku-4-5",      "display_name": "Claude Haiku",             "is_free": False, "is_default": False},
    {"provider": "litellm",   "capability": Capability.PLAN,  "model_id": "groq/llama-3.3-70b",    "display_name": "Llama 3.3 70B (LiteLLM)", "is_free": True,  "is_default": False},
    # Image models
    {"provider": "dashscope", "capability": Capability.IMAGE, "model_id": "qwen-image",            "display_name": "Qwen Image (free)",        "is_free": True,  "is_default": True},
    {"provider": "replicate", "capability": Capability.IMAGE, "model_id": "flux-schnell",           "display_name": "Flux Schnell",             "is_free": True,  "is_default": False},
    {"provider": "pexels",    "capability": Capability.IMAGE, "model_id": "pexels",                 "display_name": "Pexels Stock",             "is_free": True,  "is_default": False},
    {"provider": "openai",    "capability": Capability.IMAGE, "model_id": "gpt-image-1",            "display_name": "GPT Image 1",              "is_free": False, "is_default": False},
    # Video models
    {"provider": "dashscope", "capability": Capability.VIDEO, "model_id": "wan2.2-i2v-flash",      "display_name": "Wan Flash",                "is_free": True,  "is_default": True},
    {"provider": "dashscope", "capability": Capability.VIDEO, "model_id": "wan2.1-i2v-turbo",      "display_name": "Wan Turbo",                "is_free": False, "is_default": False},
    {"provider": "dashscope", "capability": Capability.VIDEO, "model_id": "wan2.1-i2v-plus",       "display_name": "Wan Plus",                 "is_free": False, "is_default": False},
]


class Command(BaseCommand):
    help = "Seed Provider and LLMModel tables (idempotent)"

    def handle(self, *args, **options):
        provider_map = {}
        for p in PROVIDERS:
            obj, created = Provider.objects.update_or_create(
                code=p["code"], defaults={"name": p["name"]},
            )
            provider_map[p["code"]] = obj
            self.stdout.write(f"  {'Created' if created else 'Updated'} provider: {obj.name}")

        for m in MODELS:
            provider = provider_map[m["provider"]]
            obj, created = LLMModel.objects.update_or_create(
                provider=provider, capability=m["capability"], model_id=m["model_id"],
                defaults={
                    "display_name": m["display_name"],
                    "is_free": m["is_free"],
                    "is_default": m["is_default"],
                },
            )
            self.stdout.write(f"  {'Created' if created else 'Updated'} model: {obj}")

        self.stdout.write(self.style.SUCCESS(
            f"Done — {Provider.objects.count()} providers, {LLMModel.objects.count()} models"
        ))
