"""Coverage for run_image_stage — success marks the scene DONE, a non-transient
generate_scene failure marks just that scene FAILED without aborting the run
(so transition_to_image_review still fires and the user can regenerate it).

Formerly exercised indirectly through the now-deleted orchestration._dispatch
wrapper; these call the production task directly.
"""
import os

from django.conf import settings
from django.test import TestCase
from unittest.mock import patch

from apps.accounts.models import UserAPIKey
from apps.core.models import Provider
from apps.projects.choices import Capability, MediaStatus, Status
from apps.projects.models import LLMModel, Scene
from apps.projects.tasks import run_image_stage
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


class RunImageStageTest(TestCase):
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
    def test_success_marks_scenes_done(self, mock_gen):
        project = self._make_project_with_key(scene_count=2)
        for idx in range(2):
            run_image_stage(str(project.id), idx)
        for scene in Scene.objects.filter(project=project):
            self.assertEqual(scene.media_status, MediaStatus.DONE)

    @patch("apps.projects.tasks.generate_scene", side_effect=RuntimeError("boom"))
    def test_non_transient_failure_marks_scene_failed_project_stays_generating(self, mock_gen):
        project = self._make_project_with_key(scene_count=1)
        # Non-transient failure returns (doesn't raise) so the chain continues.
        run_image_stage(str(project.id), 0)
        scene = Scene.objects.get(project=project)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)
        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)

    @patch("apps.projects.tasks.generate_scene", side_effect=_mock_generate_scene)
    def test_does_not_change_project_status(self, mock_gen):
        project = self._make_project_with_key(scene_count=1)
        run_image_stage(str(project.id), 0)
        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)
