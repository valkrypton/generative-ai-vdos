from django.test import TestCase


class SessionSmokeTest(TestCase):
    def test_session_middleware_in_settings(self):
        from django.conf import settings
        self.assertIn(
            "django.contrib.sessions.middleware.SessionMiddleware",
            settings.MIDDLEWARE,
        )

    def test_accounts_app_registered(self):
        from django.apps import apps
        self.assertIn("accounts", [a.label for a in apps.get_app_configs()])
