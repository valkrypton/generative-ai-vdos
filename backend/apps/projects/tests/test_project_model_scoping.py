"""Regression tests for attaching LLMModels to a project (serializers.ScopedModelSlugField):

- a user cannot attach another user's private model (scoping);
- a duplicate model_id resolves deterministically instead of 500-ing;
- the project list endpoint doesn't N+1 on the three model FKs.
"""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import UserProfile
from apps.core.models import Provider
from apps.projects.choices import Capability, Status
from apps.projects.models import LLMModel, Project


def _user(sub):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@example.com")


class AttachModelScopingTest(TestCase):
    def setUp(self):
        self.owner = _user("owner-scope")
        self.other = _user("other-scope")
        self.provider = Provider.objects.create(code="openai", name="OpenAI")
        session = self.client.session
        session["cognito_sub"] = self.owner.cognito_sub
        session.save()

    def test_cannot_attach_other_users_private_model(self):
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="secret-model", display_name="Theirs", owner=self.other,
        )
        resp = self.client.post(
            "/api/projects/",
            data={"prompt": "hi", "image_model": "secret-model"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("image_model", resp.json())

    def test_duplicate_model_id_resolves_to_global_without_500(self):
        # Same model_id on a global row and this user's own custom row — the old
        # unscoped .get() raised MultipleObjectsReturned -> 500.
        global_row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="dup", display_name="Global", owner=None,
        )
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="dup", display_name="Mine", owner=self.owner,
        )
        resp = self.client.post(
            "/api/projects/",
            data={"prompt": "hi", "image_model": "dup"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        project = Project.objects.get(id=resp.json()["id"])
        self.assertEqual(project.image_model_id, global_row.id)


class ProjectListQueryCountTest(TestCase):
    def setUp(self):
        self.owner = _user("owner-nplus1")
        self.provider = Provider.objects.create(code="openai", name="OpenAI")
        self.model = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="m", display_name="M", owner=None,
        )
        session = self.client.session
        session["cognito_sub"] = self.owner.cognito_sub
        session.save()

    def _make_project(self):
        Project.objects.create(
            owner=self.owner, prompt="p", status=Status.REVIEW,
            image_model=self.model,
        )

    def test_list_query_count_is_constant_as_projects_grow(self):
        self._make_project()
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self.client.get("/api/projects/").status_code, 200)

        for _ in range(4):
            self._make_project()
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.client.get("/api/projects/").status_code, 200)

        self.assertEqual(
            len(one.captured_queries), len(many.captured_queries),
            "project list must not issue extra queries per project (N+1)",
        )
