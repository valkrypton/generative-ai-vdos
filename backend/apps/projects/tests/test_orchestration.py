import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import UserAPIKey
from apps.core.models import Provider
from apps.projects.choices import Capability, MediaStatus, Status
from apps.projects.models import LLMModel, Project, Scene
from apps.projects.orchestration import run_assembly, run_images, run_voice
from apps.projects.tests.helpers import make_generating_project
from pipeline.secure import get_fernet


def _mock_generate_scene(project, scene, scene_index, secure_key, llm):
    """Simulate what generate_scene does on success: mark scene DONE."""
    scene.media_status = MediaStatus.DONE
    scene.media_path = f"scenes/test/scene_{scene_index:02d}.png"
    scene.media_provider = "placeholder"
    scene.save(update_fields=["media_path", "media_status", "media_provider", "updated_at"])
    return scene.media_path


def _make_image_model():
    provider = Provider.objects.create(code="dashscope", name="DashScope")
    return LLMModel.objects.create(
        provider=provider, capability=Capability.IMAGE,
        model_id="qwen-image-2.0", display_name="Qwen Image",
        is_free=True, is_default=True,
    )


class RunImagesTest(TestCase):
    def setUp(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        get_fernet.cache_clear()

    def tearDown(self):
        get_fernet.cache_clear()

    def _make_project_with_key(self, scene_count):
        im = _make_image_model()
        project = make_generating_project(scene_count=scene_count, image_model=im)
        key = UserAPIKey(owner=project.owner, provider=im.provider)
        key.set_api_key("sk-test-key-12345678")
        key.save()
        return project

    @patch("apps.projects.tasks.generate_scene", side_effect=_mock_generate_scene)
    def test_images_marks_scenes_done(self, mock_gen):
        project = self._make_project_with_key(scene_count=2)

        run_images(project.id, 2)

        for scene in Scene.objects.filter(project=project):
            self.assertEqual(scene.media_status, MediaStatus.DONE)

    @patch("apps.projects.tasks.generate_scene", side_effect=RuntimeError("boom"))
    def test_images_failure_marks_scene_failed_project_stays_generating(self, mock_gen):
        # Non-transient scene failures no longer abort the chain — the task returns
        # instead of raising so transition_to_image_review still fires, giving the
        # user a chance to regenerate the failed scene.
        project = self._make_project_with_key(scene_count=1)

        run_images(project.id, 1)

        scene = Scene.objects.get(project=project)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)
        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)

    @patch("apps.projects.tasks.generate_scene", side_effect=_mock_generate_scene)
    def test_images_does_not_trigger_voice(self, mock_gen):
        project = self._make_project_with_key(scene_count=1)

        run_images(project.id, 1)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)


class RunVoiceTest(TestCase):
    @patch("apps.projects.tasks.generate_all_scene_voices")
    def test_voice_success(self, mock_voice):
        project = make_generating_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)
        mock_voice.assert_called_once()

    @patch("apps.projects.tasks.generate_all_scene_voices", side_effect=RuntimeError("boom"))
    def test_voice_failure_marks_project_failed(self, mock_voice):
        project = make_generating_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)


class RunAssemblyTest(TestCase):
    @patch("apps.projects.tasks.pick_music", return_value=None)
    @patch("apps.projects.tasks.assemble")
    @patch("apps.projects.tasks.materialize_work_dir")
    def test_assembly_marks_done(self, mock_materialize, mock_assemble, _pick):
        import tempfile
        from pipeline.schema import ShotPlan

        work_dir = Path(tempfile.mkdtemp())
        final = work_dir / "final.mp4"
        final.write_bytes(b"mp4")
        plan = ShotPlan(
            title="T",
            description="d",
            tags=["t"],
            music_mood="calm",
            style_prefix="cinematic",
            scenes=[],
        )
        mock_materialize.return_value = (work_dir, plan)
        mock_assemble.return_value = final
        project = make_generating_project()
        Project.objects.filter(pk=project.pk).update(status=Status.VIDEO_GENERATING)
        project.refresh_from_db()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.DONE)

    @patch("apps.projects.tasks.materialize_work_dir", side_effect=RuntimeError("boom"))
    def test_assembly_failure_marks_project_failed(self, mock_materialize):
        project = make_generating_project()
        Project.objects.filter(pk=project.pk).update(status=Status.VIDEO_GENERATING)
        project.refresh_from_db()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
