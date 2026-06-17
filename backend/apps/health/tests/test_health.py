from django.test import TestCase


class HealthCheckTest(TestCase):
    def test_health_returns_200(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)

    def test_health_returns_json_ok(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.json(), {"status": "ok"})
