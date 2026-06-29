import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from apps.projects.constants import MediaStatus, Status
from apps.projects.models import Scene
from apps.projects.orchestration import run_assembly, run_images, run_voice
from apps.projects.tests.helpers import make_generating_project


def _mock_generate_scene(project, scene, scene_index):
    """Simulate what generate_scene does on success: mark scene DONE."""
    scene.media_status = MediaStatus.DONE
    scene.media_path = f"scenes/test/scene_{scene_index:02d}.png"
    scene.media_provider = "placeholder"
    scene.save(update_fields=["media_path", "media_status", "media_provider", "updated_at"])
    return scene.media_path


class RunImagesTest(TestCase):
    @patch("apps.projects.tasks.generate_scene", side_effect=_mock_generate_scene)
    def test_images_marks_scenes_done(self, mock_gen):
        project = make_generating_project(scene_count=2)

        run_images(project.id, 2)

        for scene in Scene.objects.filter(project=project):
            self.assertEqual(scene.media_status, MediaStatus.DONE)

    @patch("apps.projects.tasks.generate_scene", side_effect=RuntimeError("boom"))
    def test_images_failure_marks_project_failed(self, mock_gen):
        project = make_generating_project(scene_count=1)

        run_images(project.id, 1)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)

    @patch("apps.projects.tasks.generate_scene", side_effect=_mock_generate_scene)
    def test_images_does_not_trigger_voice(self, mock_gen):
        project = make_generating_project(scene_count=1)

        run_images(project.id, 1)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)


class RunVoiceTest(TestCase):
    @patch("apps.projects.tasks.get_work_dir")
    def test_voice_success(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = make_generating_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)

    @patch("apps.projects.tasks.get_work_dir")
    def test_voice_failure_marks_project_failed(self, mock_work_dir):
        mock_work_dir.side_effect = RuntimeError("boom")
        project = make_generating_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)


class RunAssemblyTest(TestCase):
    @patch("apps.projects.tasks.get_work_dir")
    def test_assembly_marks_done(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = make_generating_project()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.DONE)

    @patch("apps.projects.tasks.get_work_dir")
    def test_assembly_failure_marks_project_failed(self, mock_work_dir):
        mock_work_dir.side_effect = RuntimeError("boom")
        project = make_generating_project()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
