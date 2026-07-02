import os

from django.conf import settings
from django.test import TestCase

from apps.accounts.models import UserAPIKey, UserProfile
from apps.core.models import Provider
from apps.projects.choices import Capability
from apps.projects.models import LLMModel
from pipeline.secure import get_fernet


def _user(sub="owner-sub"):
    return UserProfile.objects.create(cognito_sub=sub, email=f"{sub}@example.com")


def _provider(code="openai", name="OpenAI"):
    return Provider.objects.create(code=code, name=name)


def _key(user, provider):
    key = UserAPIKey(owner=user, provider=provider)
    key.set_api_key("sk-test-key-12345678")
    key.save()
    return key


class LLMModelViewSetTest(TestCase):
    def setUp(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = settings.FIELD_ENCRYPTION_KEY
        get_fernet.cache_clear()
        self.user = _user("owner-sub")
        self.provider = _provider()
        self.url = "/api/models/"

    def tearDown(self):
        get_fernet.cache_clear()

    def _login_as(self, sub):
        session = self.client.session
        session["cognito_sub"] = sub
        session.save()

    def test_unauthenticated_cannot_list(self):
        resp = self.client.get(self.url)
        self.assertIn(resp.status_code, (401, 403))

    def test_list_includes_global_and_own_rows_only(self):
        other = _user("other-sub")
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="global-model", display_name="Global",
        )
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="theirs", display_name="Theirs", owner=other,
        )
        self._login_as("owner-sub")
        resp = self.client.get(self.url)
        model_ids = {row["model_id"] for row in resp.json()}
        self.assertEqual(model_ids, {"global-model", "mine"})

    def test_list_marks_owned_flag(self):
        LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        self._login_as("owner-sub")
        resp = self.client.get(self.url)
        row = resp.json()[0]
        self.assertTrue(row["owned"])

    def test_create_requires_matching_api_key(self):
        self._login_as("owner-sub")
        resp = self.client.post(self.url, {
            "provider": self.provider.id, "capability": "image",
            "model_id": "custom-1", "display_name": "Custom One",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(LLMModel.objects.filter(model_id="custom-1").exists())

    def test_create_succeeds_with_api_key(self):
        _key(self.user, self.provider)
        self._login_as("owner-sub")
        resp = self.client.post(self.url, {
            "provider": self.provider.id, "capability": "image",
            "model_id": "custom-1", "display_name": "Custom One",
        }, content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        row = LLMModel.objects.get(model_id="custom-1")
        self.assertEqual(row.owner, self.user)
        self.assertFalse(row.is_free)
        self.assertFalse(row.is_default)
        self.assertEqual(resp.json()["provider"], "openai")

    def test_delete_own_row_succeeds(self):
        _key(self.user, self.provider)
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="mine", display_name="Mine", owner=self.user,
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(LLMModel.objects.filter(pk=row.pk).exists())

    def test_delete_global_row_forbidden(self):
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="global-model", display_name="Global",
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(LLMModel.objects.filter(pk=row.pk).exists())

    def test_delete_other_users_row_not_found(self):
        other = _user("other-sub")
        row = LLMModel.objects.create(
            provider=self.provider, capability=Capability.IMAGE,
            model_id="theirs", display_name="Theirs", owner=other,
        )
        self._login_as("owner-sub")
        resp = self.client.delete(f"{self.url}{row.id}/")
        self.assertIn(resp.status_code, (403, 404))
