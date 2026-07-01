import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# DashScope image generation is rate-limited to 2 concurrent requests account-wide
# (pipeline/images/qwen_image.py's _concurrency_slot). Routing it to its own queue,
# consumed by a worker started with --concurrency 2 (see `make prod`), lets Celery
# enforce that limit directly instead of workers busy-waiting on the Redis semaphore.
app.conf.task_routes = {
    "apps.projects.tasks.run_image_stage": {"queue": "images"},
}
app.autodiscover_tasks()
