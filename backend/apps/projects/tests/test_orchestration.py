import tempfile
import uuid as _uuid
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.projects.constants import ImageStatus, Status
from apps.projects.models import Project, Scene
from apps.projects.orchestration import run_assembly, run_images, run_voice


def _setup_project(scene_count=2):
    uid = _uuid.uuid4().hex[:8]
    user = UserProfile.objects.create(
        cognito_sub=f"sub-orch-{uid}", email=f"orch-{uid}@example.com"
    )
    project = Project.objects.create(owner=user, prompt="test")
    project.transition_status(Status.PLANNING)
    project.transition_status(Status.REVIEW)
    project.transition_status(Status.GENERATING)
    for i in range(scene_count):
        Scene.objects.create(project=project, index=i)
    return project


class RunImagesTest(TestCase):
    @patch("apps.projects.tasks.get_work_dir")
    def test_images_marks_scenes_done(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = _setup_project(scene_count=2)

        run_images(project.id, 2)

        for scene in Scene.objects.filter(project=project):
            self.assertEqual(scene.image_status, ImageStatus.DONE)

    @patch("apps.projects.tasks.get_work_dir")
    def test_images_failure_marks_project_failed(self, mock_work_dir):
        mock_work_dir.side_effect = RuntimeError("boom")
        project = _setup_project(scene_count=1)

        run_images(project.id, 1)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)

    @patch("apps.projects.tasks.get_work_dir")
    def test_images_does_not_trigger_voice(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = _setup_project(scene_count=1)

        run_images(project.id, 1)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)


class RunVoiceTest(TestCase):
    @patch("apps.projects.tasks.get_work_dir")
    def test_voice_success(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = _setup_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.GENERATING)

    @patch("apps.projects.tasks.get_work_dir")
    def test_voice_failure_marks_project_failed(self, mock_work_dir):
        mock_work_dir.side_effect = RuntimeError("boom")
        project = _setup_project()

        run_voice(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)


class RunAssemblyTest(TestCase):
    @patch("apps.projects.tasks.get_work_dir")
    def test_assembly_marks_done(self, mock_work_dir):
        mock_work_dir.return_value = Path(tempfile.mkdtemp())
        project = _setup_project()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.DONE)

    @patch("apps.projects.tasks.get_work_dir")
    def test_assembly_failure_marks_project_failed(self, mock_work_dir):
        mock_work_dir.side_effect = RuntimeError("boom")
        project = _setup_project()

        run_assembly(project.id)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
