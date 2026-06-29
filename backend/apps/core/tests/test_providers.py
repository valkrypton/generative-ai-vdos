from django.test import TestCase
from apps.core.models import Provider


class ProviderListViewTest(TestCase):
    def test_returns_active_providers(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        Provider.objects.create(code="dashscope", name="DashScope", is_active=True)
        res = self.client.get("/api/core/providers/")
        self.assertEqual(res.status_code, 200)
        codes = {p["code"] for p in res.json()}
        self.assertIn("openai", codes)
        self.assertIn("dashscope", codes)

    def test_excludes_inactive_providers(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        Provider.objects.create(code="gone", name="Gone", is_active=False)
        res = self.client.get("/api/core/providers/")
        codes = {p["code"] for p in res.json()}
        self.assertNotIn("gone", codes)

    def test_response_shape(self):
        Provider.objects.create(code="openai", name="OpenAI", is_active=True)
        res = self.client.get("/api/core/providers/")
        item = res.json()[0]
        self.assertIn("id", item)
        self.assertIn("code", item)
        self.assertIn("name", item)
        self.assertNotIn("is_active", item)
        self.assertNotIn("created_at", item)

    def test_empty_when_no_providers(self):
        res = self.client.get("/api/core/providers/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])
