import os
import urllib.parse
from unittest.mock import patch, MagicMock
from django.test import TestCase


FAKE_CONFIG = {
    "COGNITO_DOMAIN": "https://example.auth.us-east-1.amazoncognito.com",
    "COGNITO_APP_CLIENT_ID": "client-abc",
    "COGNITO_APP_CLIENT_SECRET": "secret-xyz",
    "COGNITO_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
    "COGNITO_LOGOUT_REDIRECT_URI": "http://localhost:3000",
}


class GetConfigTest(TestCase):
    def test_returns_config_when_all_vars_set(self):
        with patch.dict(os.environ, FAKE_CONFIG):
            from apps.auth_oidc.cognito import get_config
            cfg = get_config()
        self.assertEqual(cfg["COGNITO_APP_CLIENT_ID"], "client-abc")

    def test_raises_when_var_missing(self):
        from django.core.exceptions import ImproperlyConfigured
        from apps.auth_oidc.cognito import get_config
        # Provide only 4 of 5 required vars; COGNITO_DOMAIN is absent
        partial_env = {k: v for k, v in FAKE_CONFIG.items() if k != "COGNITO_DOMAIN"}
        with patch.dict(os.environ, partial_env, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                get_config()


class BuildAuthorizeUrlTest(TestCase):
    def test_contains_client_id_and_redirect(self):
        from apps.auth_oidc.cognito import build_authorize_url
        url = build_authorize_url(FAKE_CONFIG, state="abc123")
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        self.assertEqual(params["client_id"], "client-abc")
        self.assertEqual(params["state"], "abc123")
        self.assertEqual(params["response_type"], "code")
        self.assertIn("openid", params["scope"])
        self.assertTrue(url.startswith(FAKE_CONFIG["COGNITO_DOMAIN"]))

    def test_redirect_uri_in_params(self):
        from apps.auth_oidc.cognito import build_authorize_url
        url = build_authorize_url(FAKE_CONFIG, state="s")
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(params["redirect_uri"], FAKE_CONFIG["COGNITO_REDIRECT_URI"])


class ExchangeCodeTest(TestCase):
    def _mock_post(self, status_code, json_body):
        mock_resp = MagicMock()
        mock_resp.ok = status_code < 400
        mock_resp.json.return_value = json_body
        return mock_resp

    def test_returns_tokens_on_success(self):
        tokens = {
            "id_token": "id.jwt",
            "access_token": "access.jwt",
            "refresh_token": "refresh.jwt",
        }
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(200, tokens)):
            from apps.auth_oidc.cognito import exchange_code
            result = exchange_code(FAKE_CONFIG, "auth-code-123")
        self.assertEqual(result["id_token"], "id.jwt")
        self.assertEqual(result["access_token"], "access.jwt")

    def test_returns_none_on_error_response(self):
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(400, {"error": "invalid_grant"})):
            from apps.auth_oidc.cognito import exchange_code
            result = exchange_code(FAKE_CONFIG, "bad-code")
        self.assertIsNone(result)

    def test_posts_to_token_endpoint(self):
        with patch("apps.auth_oidc.cognito.requests.post",
                   return_value=self._mock_post(200, {})) as mock_post:
            from apps.auth_oidc.cognito import exchange_code
            exchange_code(FAKE_CONFIG, "code123")
        call_args = mock_post.call_args
        self.assertIn("/oauth2/token", call_args[0][0])
        self.assertEqual(call_args[1]["data"]["code"], "code123")


class BuildLogoutUrlTest(TestCase):
    def test_contains_client_id_and_logout_uri(self):
        from apps.auth_oidc.cognito import build_logout_url
        url = build_logout_url(FAKE_CONFIG)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.assertEqual(params["client_id"], "client-abc")
        self.assertEqual(params["logout_uri"], "http://localhost:3000")
        self.assertTrue(url.startswith(FAKE_CONFIG["COGNITO_DOMAIN"]))
