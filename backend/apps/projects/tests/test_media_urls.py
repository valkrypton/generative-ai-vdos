from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase

from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene
from apps.projects.serializers import SceneSerializer, _absolute_media_url


class AbsoluteMediaUrlTest(TestCase):
    def test_relative_media_path_unchanged(self):
        url = "/media/1/proj/images/scene_00.png"
        req = RequestFactory().get("/", HTTP_HOST="127.0.0.1:8000")
        self.assertEqual(_absolute_media_url(url, req), url)

    def test_presigned_url_unchanged(self):
        url = "https://bucket.s3.amazonaws.com/key?X-Amz-Signature=abc"
        self.assertEqual(_absolute_media_url(url, None), url)


class SceneSerializerMediaUrlTest(TestCase):
    def test_localhost_request_returns_relative_media_url(self):
        owner = UserProfile.objects.create(cognito_sub="sub-rel", email="rel@test.com")
        project = Project.objects.create(owner=owner, prompt="relative url test")
        scene = Scene.objects.create(project=project, index=0)
        scene.media_path.save("scene_00.png", ContentFile(b"\x89PNG"), save=True)

        req = RequestFactory().get("/api/projects/", HTTP_HOST="127.0.0.1:8000")
        data = SceneSerializer(scene, context={"request": req}).data

        self.assertTrue(data["media_path"].startswith("/media/"))
        self.assertNotIn("127.0.0.1", data["media_path"])
