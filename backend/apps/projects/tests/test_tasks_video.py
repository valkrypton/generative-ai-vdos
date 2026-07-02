from unittest.mock import MagicMock, patch

import os

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import UserAPIKey
from apps.core.models import Provider
from apps.projects.choices import Capability, MediaStatus, Status
from apps.projects.models import LLMModel, Project, Scene
from apps.projects.tasks import run_video_stage
from apps.projects.tests.helpers import make_project, make_shot_plan


def _make_video_model():
    provider = Provider.objects.create(code="dashscope", name="DashScope")
    return LLMModel.objects.create(
        provider=provider, capability=Capability.VIDEO,
        model_id="wan2.2-i2v-flash", display_name="Wan Flash",
        is_free=True, is_default=True,
    )


def _make_animated_project(video_model=None):
    """Project in GENERATING state with one animated scene and one still scene."""
    project = make_project(shot_plan=make_shot_plan(2), video_model=video_model)
    Project.objects.filter(pk=project.pk).update(status=Status.GENERATING)
    project.refresh_from_db()
    Scene.objects.create(
        project=project, index=0,
        narration="animated narration", media_prompt="flying dragon",
        animate=True, media_path="scenes/test/scene_00.png",
    )
    Scene.objects.create(
        project=project, index=1,
        narration="still narration", media_prompt="mountain valley",
        animate=False, media_path="scenes/test/scene_01.png",
    )
    return project


def _mock_storage(fake_bytes=b"\x89PNG\r\n\x1a\n"):
    mock = MagicMock()
    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=mock_file)
    mock_file.__exit__ = MagicMock(return_value=False)
    mock_file.read.return_value = fake_bytes
    mock.storage.open.return_value = mock_file
    return mock


FAKE_MP4 = b"fake-mp4-bytes"


class RunVideoStageSkipTest(TestCase):
    def test_no_animated_scenes_returns_early(self):
        """No animate=True scenes → task publishes skip event without calling submit."""
        vm = _make_video_model()
        project = make_project(shot_plan=make_shot_plan(1), video_model=vm)
        Project.objects.filter(pk=project.pk).update(status=Status.GENERATING)
        Scene.objects.create(project=project, index=0, narration="n",
                             media_prompt="p", animate=False,
                             media_path="scenes/test/scene_00.png")

        with patch("pipeline.video.wan.WanProvider.submit") as mock_submit:
            run_video_stage(str(project.id))
            mock_submit.assert_not_called()


class RunVideoStageHappyPathTest(TestCase):
    @patch("apps.projects.utils._motion_prompt", return_value="gentle cinematic motion")
    @patch("pipeline.video.wan.WanProvider.download")
    @patch("pipeline.video.wan.WanProvider.poll", return_value="https://cdn.example.com/clip.mp4")
    @patch("pipeline.video.wan.WanProvider.submit", return_value="task_abc123")
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_animates_scene_and_marks_done(
        self, mock_time, mock_storage, mock_submit, mock_poll, mock_download, mock_motion,
    ):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        # Arrange storage: open returns PNG bytes, upload is a no-op mock
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file
        mock_download.side_effect = lambda url, path: path.write_bytes(FAKE_MP4)

        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)
        api_key = UserAPIKey(owner=project.owner, provider=vm.provider)
        api_key.set_api_key("sk-test-dashscope-key12")
        api_key.save()

        run_video_stage(str(project.id))

        mock_submit.assert_called_once()
        mock_poll.assert_called_with("task_abc123", api_key.get_secure_key())
        mock_storage.upload.assert_called_once()

        animated = Scene.objects.get(project=project, index=0)
        self.assertEqual(animated.media_status, MediaStatus.DONE)
        self.assertEqual(animated.media_provider, "wan-i2v")

        still = Scene.objects.get(project=project, index=1)
        self.assertEqual(still.media_status, MediaStatus.PENDING)

    @patch("apps.projects.utils._motion_prompt", return_value="gentle cinematic motion")
    @patch("pipeline.video.wan.WanProvider.download")
    @patch("pipeline.video.wan.WanProvider.poll", return_value="https://cdn.example.com/clip.mp4")
    @patch("pipeline.video.wan.WanProvider.submit", return_value="task_sec123")
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_animates_scene_with_user_api_key(
        self, mock_time, mock_storage, mock_submit, mock_poll, mock_download, mock_motion,
    ):
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file
        mock_download.side_effect = lambda url, path: path.write_bytes(FAKE_MP4)

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)
        api_key = UserAPIKey(owner=project.owner, provider=vm.provider)
        api_key.set_api_key("sk-test-dashscope-key12")
        api_key.save()
        secure_key = api_key.get_secure_key()

        run_video_stage(str(project.id))

        mock_submit.assert_called_once()
        self.assertEqual(mock_submit.call_args[0][2].decrypt(), secure_key.decrypt())
        mock_poll.assert_called_with("task_sec123", secure_key)


class RunVideoStageFailureTest(TestCase):
    @patch("apps.projects.utils._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.submit", side_effect=RuntimeError("API down"))
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_submit_failure_marks_scene_and_project_failed(
        self, mock_time, mock_storage, mock_submit, mock_motion,
    ):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file

        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)
        api_key = UserAPIKey(owner=project.owner, provider=vm.provider)
        api_key.set_api_key("sk-test-dashscope-key12")
        api_key.save()

        run_video_stage(str(project.id))

        scene = Scene.objects.get(project=project, index=0)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("All animated scene submissions failed", project.error)

    def test_no_video_model_marks_project_failed(self):
        project = _make_animated_project(video_model=None)

        run_video_stage(str(project.id))

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("No video model", project.error)

    @patch("apps.projects.utils._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.poll", side_effect=RuntimeError("poll failed"))
    @patch("pipeline.video.wan.WanProvider.submit", return_value="task_xyz")
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_poll_failure_marks_scene_and_project_failed(
        self, mock_time, mock_storage, mock_submit, mock_poll, mock_motion,
    ):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file

        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)
        api_key = UserAPIKey(owner=project.owner, provider=vm.provider)
        api_key.set_api_key("sk-test-dashscope-key12")
        api_key.save()

        run_video_stage(str(project.id))

        scene = Scene.objects.get(project=project, index=0)
        self.assertEqual(scene.media_status, MediaStatus.FAILED)


class RunVideoStageMissingKeyTest(TestCase):
    @patch("apps.projects.utils._motion_prompt", return_value="prompt")
    @patch("pipeline.video.wan.WanProvider.submit")
    @patch("apps.projects.utils.storage_provider")
    @patch("apps.projects.utils.time")
    def test_no_key_marks_scene_failed(self, mock_time, mock_storage, mock_submit, mock_motion):
        mock_time.time.return_value = 0
        mock_time.sleep = MagicMock()
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG\r\n\x1a\n"
        mock_storage.storage.open.return_value = mock_file

        vm = _make_video_model()
        project = _make_animated_project(video_model=vm)

        run_video_stage(str(project.id))

        mock_submit.assert_not_called()
        # The key is now resolved once per stage, before the per-scene loop —
        # a missing key fails the whole stage immediately, so the scene is
        # never touched (stays PENDING) while the project is marked FAILED.
        animated = Scene.objects.get(project=project, index=0)
        self.assertEqual(animated.media_status, MediaStatus.PENDING)

        project.refresh_from_db()
        self.assertEqual(project.status, Status.FAILED)
        self.assertIn("All animated scene submissions failed", project.error)
