import logging
import tempfile
import time
from pathlib import Path

from django.conf import settings
from apps.storage import storage_provider
from django.db import transaction

from apps.accounts.models import UserAPIKey
from apps.projects.choices import Capability, MediaStatus, Level, Stage, Status, VoiceStatus
from apps.projects.models import LLMModel, Project, Scene
from apps.projects.services import publish_event

from pipeline.images import generate_scene_image, get_provider
from pipeline.schema import ShotPlan
from pipeline.script_agent import consistency_review, polish_image_prompts
from pipeline.video import _motion_prompt
from pipeline.video.wan import WanProvider
from pipeline.voiceover import DEFAULT_VOICE, generate_voiceover, resolve_voice, synth_scene_sync

_VIDEO_POLL_INTERVAL = 15       # seconds between poll ticks
_VIDEO_POLL_TIMEOUT = 15 * 60   # max wait per batch

logger = logging.getLogger(__name__)


def get_work_dir(project):
    # Must be outside MEDIA_ROOT so _download_field never copies a file onto
    # its own storage path (open-for-write truncates before open-for-read).
    base = Path(settings.BASE_DIR).parent / "workdirs"
    return base / str(project.owner_id) / str(project.id)


def scene_payload(scene, *, include_voice: bool = False) -> dict:
    """One Scene row -> a plan-scene dict for ShotPlan.model_validate.

    Shared by build_shot_plan, animate_scene and run_refine_stage so the payload
    shape can't drift between them. Only voiceover generation needs the per-scene
    voice, so it's opt-in.
    """
    data = {
        "media_prompt": scene.media_prompt,
        "narration": scene.narration,
        "negative_prompt": scene.negative_prompt or None,
        "animate": scene.animate,
        "on_screen_text": scene.on_screen_text or None,
    }
    if include_voice:
        data["voice"] = scene.voice or None
    return data


def build_shot_plan(project) -> ShotPlan:
    """Merge plan-level metadata with Scene rows — single source of truth."""
    plan_data = {**(project.shot_plan or {})}
    plan_data.setdefault("title", project.title or "Untitled")
    plan_data.setdefault("description", "")
    plan_data.setdefault("tags", [])
    plan_data.setdefault("style_prefix", "")
    if not plan_data.get("music_mood") and project.music:
        plan_data["music_mood"] = project.music
    plan_data.setdefault("music_mood", "calm")
    plan_data["scenes"] = [
        scene_payload(scene, include_voice=True)
        for scene in Scene.objects.filter(project=project).order_by("index")
    ]
    return ShotPlan.model_validate(plan_data)


class MissingAPIKeyError(Exception):
    """Raised when a project's owner has no API key configured for a required provider."""


def resolve_secure_key(owner, provider):
    try:
        return UserAPIKey.objects.get(
            owner=owner, provider=provider,
        ).get_secure_key()
    except UserAPIKey.DoesNotExist:
        raise MissingAPIKeyError(
            f"No API key configured for {provider.name} — add one in Settings."
        )


def resolve_plan_model(project):
    llm = project.plan_model or LLMModel.objects.filter(
        capability=Capability.PLAN, is_default=True, is_active=True,
    ).select_related("provider").first()

    if not llm:
        raise RuntimeError("No plan model assigned and no default plan model configured.")

    return llm


def polish_plan(plan, model_id, provider_code, secure_key, animate=True):
    plan = polish_image_prompts(plan, model=model_id,
                                provider=provider_code, api_key=secure_key)
    plan = consistency_review(plan, model=model_id, animate=animate,
                              provider=provider_code, api_key=secure_key)
    return plan


def save_plan(project, plan):
    with transaction.atomic():
        # Scenes are the DB source of truth; shot_plan stores only plan-level metadata.
        project.shot_plan = plan.model_dump(exclude={"scenes"})
        project.title = plan.title
        project.save(update_fields=["shot_plan", "title", "updated_at"])

        project.scenes.all().delete()
        Scene.objects.bulk_create([
            Scene(
                project=project,
                index=i,
                narration=scene.narration,
                media_prompt=scene.media_prompt,
                on_screen_text=scene.on_screen_text or "",
                negative_prompt=scene.negative_prompt or "",
                animate=scene.animate,
                voice=scene.voice or "",
            )
            for i, scene in enumerate(plan.scenes)
        ])


def fetch_project_for_plan(project_id):
    try:
        return Project.objects.select_related(
            "plan_model", "plan_model__provider", "owner",
        ).get(id=project_id)
    except Project.DoesNotExist:
        logger.error("Project %s not found, aborting stage", project_id)
        return None


def handle_transient_error(task, project, project_id, stage, exc):
    retries_left = task.max_retries - task.request.retries
    if retries_left > 0:
        logger.warning("%s stage transient error, %d retries left: %s", stage, retries_left, exc)
        raise
    fail_project(project, project_id, stage, exc)


def fail_project(project, project_id, stage, exc):
    error_type = type(exc).__name__
    error_message = f"[{error_type}] {exc}"
    logger.error("%s stage failed: %s", stage, error_message)
    project.error = error_message[:2000]
    project.save(update_fields=["error", "updated_at"])
    project.transition_status(Status.FAILED)
    publish_event(project_id, stage, Level.ERROR, error_message[:500])


def generate_scene(project, scene, scene_index, secure_key, llm):
    project_id = project.id
    plan = build_shot_plan(project)

    provider = get_provider(llm.provider.code, api_key=secure_key)

    scene.media_status = MediaStatus.RUNNING
    scene.save(update_fields=["media_status", "updated_at"])
    publish_event(
        project_id, Stage.IMAGES, Level.INFO,
        f"Generating image for scene {scene_index} via {provider.name} ({llm.model_id})",
        scene_index=scene_index,
        media_status=MediaStatus.RUNNING,
    )

    def _on_preview(url: str) -> None:
        scene.preview_url = url
        scene.save(update_fields=["preview_url", "updated_at"])
        publish_event(
            project_id, Stage.IMAGES, Level.INFO,
            f"Scene {scene_index} preview ready",
            scene_index=scene_index,
            preview_url=url,
            media_status=MediaStatus.RUNNING,
        )

    data, used = generate_scene_image(
        plan, scene_index, provider,
        fallback=False,
        api_key=secure_key,
        model=llm.model_id,
        on_preview_url=_on_preview,
    )
    if not data:
        raise RuntimeError(f"image provider {used.name} returned empty bytes for scene {scene_index}")

    if scene.media_path:
        scene.media_path.delete(save=False)

    filename = f"scene_{scene_index:02d}.png"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / filename
            tmp_path.write_bytes(data)
            storage_provider.upload(scene.media_path, tmp_path, save=False)
    except Exception as e:
        logger.error("Failed to upload image to storage: %s", e)
        scene.preview_url = ""
        scene.media_status = MediaStatus.FAILED
        scene.save(update_fields=["preview_url", "media_status", "updated_at"])
        publish_event(
            project_id, Stage.IMAGES, Level.ERROR,
            f"Failed to upload image for scene {scene_index}: {e}",
            scene_index=scene_index,
            media_status=MediaStatus.FAILED,
        )
        raise

    scene.preview_url = ""
    scene.media_status = MediaStatus.DONE
    scene.media_provider = used.name
    scene.save(update_fields=[
        "preview_url", "media_path", "media_status", "media_provider", "updated_at"
    ])
    publish_event(
        project_id, Stage.IMAGES, Level.INFO,
        f"Scene {scene_index} image done via {used.name}",
        scene_index=scene_index,
        media_status=MediaStatus.DONE,
    )
    return scene.media_path.name


def animate_scene(project, scene, scene_index, secure_key):
    project_id = project.id

    plan_data = {**(project.shot_plan or {})}
    plan_data["scenes"] = [
        scene_payload(s)
        for s in Scene.objects.filter(project=project).order_by("index")
    ]
    plan = ShotPlan.model_validate(plan_data)
    provider = WanProvider()

    scene.media_status = MediaStatus.RUNNING
    scene.save(update_fields=["media_status", "updated_at"])
    publish_event(project_id, Stage.VIDEO, Level.INFO,
                  f"Animating scene {scene_index}",
                  scene_index=scene_index, media_status=MediaStatus.RUNNING)

    filename = f"scene_{scene_index:02d}.png"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / filename
        with storage_provider.storage.open(scene.media_path.name, "rb") as f:
            tmp_path.write_bytes(f.read())
        prompt = _motion_prompt(plan, plan.scenes[scene_index])
        task_id = provider.submit(prompt, tmp_path, secure_key)

    publish_event(project_id, Stage.VIDEO, Level.INFO,
                  f"Scene {scene_index} submitted (task {task_id})")

    deadline = time.time() + _VIDEO_POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(_VIDEO_POLL_INTERVAL)
        url = provider.poll(task_id, secure_key)
        if url:
            filename = f"scene_{scene_index:02d}.mp4"
            with tempfile.TemporaryDirectory() as tmpdir:
                mp4_path = Path(tmpdir) / filename
                provider.download(url, mp4_path)
                if scene.media_path:
                    scene.media_path.delete(save=False)
                storage_provider.upload(scene.media_path, mp4_path, save=False)
            scene.media_status = MediaStatus.DONE
            scene.media_provider = provider.name
            scene.save(update_fields=["media_path", "media_status", "media_provider", "updated_at"])
            publish_event(project_id, Stage.VIDEO, Level.INFO,
                          f"Scene {scene_index} animated via {provider.name}",
                          scene_index=scene_index, media_status=MediaStatus.DONE)
            return

    raise RuntimeError(f"Scene {scene_index} timed out after {_VIDEO_POLL_TIMEOUT // 60} min")


def _upload_voice_files(scene, mp3_path: Path, words_path: Path) -> None:
    old_audio_name = scene.audio_path.name if scene.audio_path else ""
    old_words_name = scene.words_path.name if scene.words_path else ""
    storage_provider.upload(scene.audio_path, mp3_path, save=False)
    storage_provider.upload(scene.words_path, words_path, save=False)
    scene.voice_status = VoiceStatus.DONE
    scene.save(update_fields=["audio_path", "words_path", "voice_status", "updated_at"])
    if old_audio_name and old_audio_name != scene.audio_path.name:
        storage_provider.storage.delete(old_audio_name)
    if old_words_name and old_words_name != scene.words_path.name:
        storage_provider.storage.delete(old_words_name)


def generate_all_scene_voices(project):
    """Synthesize every scene in one edge-tts session, then upload to storage."""
    project_id = project.id
    plan = build_shot_plan(project)
    audio_dir = get_work_dir(project) / "audio"
    default_voice = project.narrator_voice or DEFAULT_VOICE
    scenes = list(Scene.objects.filter(project=project).order_by("index"))

    try:
        generate_voiceover(plan, audio_dir, voice=default_voice)
        for scene in scenes:
            idx = scene.index
            mp3_path = audio_dir / f"scene_{idx:02d}.mp3"
            words_path = audio_dir / f"scene_{idx:02d}.words.json"
            if not mp3_path.is_file() or not words_path.is_file():
                raise FileNotFoundError(f"voiceover output missing for scene {idx}")
            scene.voice_status = VoiceStatus.RUNNING
            scene.save(update_fields=["voice_status", "updated_at"])
            publish_event(
                project_id, Stage.VOICE, Level.INFO,
                f"Uploading voiceover for scene {idx}",
                scene_index=idx,
            )
            _upload_voice_files(scene, mp3_path, words_path)
            publish_event(
                project_id, Stage.VOICE, Level.INFO,
                f"Scene {idx} voiceover done",
                scene_index=idx,
            )
    except Exception:
        Scene.objects.filter(
            pk__in=[scene.pk for scene in scenes],
            voice_status__in=[VoiceStatus.PENDING, VoiceStatus.RUNNING],
        ).update(voice_status=VoiceStatus.FAILED)
        raise


def generate_scene_voice(project, scene, scene_index):
    project_id = project.id
    default_voice = project.narrator_voice or DEFAULT_VOICE
    voice = resolve_voice(scene.voice or None, default_voice)

    scene.voice_status = VoiceStatus.RUNNING
    scene.save(update_fields=["voice_status", "updated_at"])
    publish_event(
        project_id, Stage.VOICE, Level.INFO,
        f"Generating voiceover for scene {scene_index} ({voice})",
        scene_index=scene_index,
    )

    mp3_name = f"scene_{scene_index:02d}.mp3"
    words_name = f"scene_{scene_index:02d}.words.json"
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / mp3_name
            words_path = Path(tmpdir) / words_name
            synth_scene_sync(scene.narration, voice, mp3_path, words_path)
            _upload_voice_files(scene, mp3_path, words_path)
    except Exception as e:
        logger.error("Voiceover failed for scene %s: %s", scene_index, e)
        scene.voice_status = VoiceStatus.FAILED
        scene.save(update_fields=["voice_status", "updated_at"])
        publish_event(
            project_id, Stage.VOICE, Level.ERROR,
            f"Scene {scene_index} voiceover failed: {e}",
            scene_index=scene_index,
        )
        raise

    publish_event(
        project_id, Stage.VOICE, Level.INFO,
        f"Scene {scene_index} voiceover done",
        scene_index=scene_index,
    )
    return scene.audio_path.name
