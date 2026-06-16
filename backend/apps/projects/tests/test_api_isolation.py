from django.test import TestCase
from apps.accounts.models import UserProfile
from apps.projects.models import Project, Scene


def make_user(sub):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@example.com")


class SceneIsolationTest(TestCase):
    """Scenes must only be reachable by the project's owner (regression for IDOR)."""

    def setUp(self):
        self.owner = make_user("owner-sub")
        self.project = Project.objects.create(owner=self.owner, prompt="p")
        self.scene = Scene.objects.create(project=self.project, index=0)
        self.url = f"/api/projects/{self.project.id}/scenes/"

    def _login_as(self, sub):
        session = self.client.session
        session["cognito_sub"] = sub
        session.save()

    def test_unauthenticated_cannot_list_scenes(self):
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (401, 403))

    def test_other_user_cannot_list_scenes(self):
        make_user("attacker-sub")
        self._login_as("attacker-sub")
        resp = self.client.get(self.url)
        self.assertEqual(resp.json(), [])

    def test_owner_can_list_scenes(self):
        self._login_as("owner-sub")
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.json()), 1)


class ProjectIsolationTest(TestCase):
    def setUp(self):
        self.owner = make_user("p-owner")
        self.project = Project.objects.create(owner=self.owner, prompt="p")

    def _login_as(self, sub):
        session = self.client.session
        session["cognito_sub"] = sub
        session.save()

    def test_other_user_cannot_retrieve_project(self):
        make_user("p-attacker")
        self._login_as("p-attacker")
        resp = self.client.get(f"/api/projects/{self.project.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_other_user_list_is_empty(self):
        make_user("p-attacker2")
        self._login_as("p-attacker2")
        resp = self.client.get("/api/projects/")
        self.assertEqual(resp.json(), [])

    def test_unauthenticated_list_is_denied(self):
        resp = self.client.get("/api/projects/")
        self.assertIn(resp.status_code, (401, 403))
