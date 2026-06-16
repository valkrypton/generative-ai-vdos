import base64
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.accounts.models import UserProfile


FAKE_COGNITO = {
    "COGNITO_DOMAIN": "https://example.auth.us-east-1.amazoncognito.com",
    "COGNITO_APP_CLIENT_ID": "client-abc",
    "COGNITO_APP_CLIENT_SECRET": "secret-xyz",
    "COGNITO_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
    "COGNITO_LOGOUT_REDIRECT_URI": "http://localhost:3000",
}


def _make_fake_jwt(claims: dict) -> str:
    def b64url(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{b64url({'alg': 'none'})}.{b64url(claims)}."


def _mock_exchange(tokens):
    mock_resp = MagicMock()
    mock_resp.ok = tokens is not None
    if tokens is not None:
        mock_resp.json.return_value = tokens
    return patch("apps.accounts.cognito.requests.post", return_value=mock_resp)


class CallbackGuardTest(TestCase):
    def _set_state(self, state="s"):
        session = self.client.session
        session["cognito_state"] = state
        session.save()

    def _callback(self, tokens):
        self._set_state("s")
        with self.settings(COGNITO=FAKE_COGNITO), _mock_exchange(tokens):
            return self.client.get("/api/auth/callback", {"code": "c", "state": "s"})

    def test_missing_id_token_returns_401(self):
        # 200 token response without id_token must not 500 (#5)
        resp = self._callback({"access_token": "a", "refresh_token": "r"})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(UserProfile.objects.exists())

    def test_malformed_id_token_returns_401(self):
        resp = self._callback({"id_token": "not-a-jwt", "access_token": "a"})
        self.assertEqual(resp.status_code, 401)

    def test_token_without_sub_returns_401(self):
        # No sub claim → reject, don't collapse onto an empty-sub profile (#4)
        token = _make_fake_jwt({"email": "x@example.com"})
        resp = self._callback({"id_token": token, "access_token": "a"})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(UserProfile.objects.filter(cognito_sub="").exists())

    def test_session_key_rotates_on_login(self):
        # Session fixation defense: key must change across the auth boundary (#6)
        self._set_state("s")
        pre_key = self.client.session.session_key
        token = _make_fake_jwt({"sub": "abc", "email": "x@example.com"})
        with self.settings(COGNITO=FAKE_COGNITO), _mock_exchange(
            {"id_token": token, "access_token": "a", "refresh_token": "r"}
        ):
            self.client.get("/api/auth/callback", {"code": "c", "state": "s"})
        self.assertNotEqual(self.client.session.session_key, pre_key)
        self.assertEqual(self.client.session["cognito_sub"], "abc")


class MeEndpointTest(TestCase):
    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me")
        self.assertIn(resp.status_code, (401, 403))

    def test_me_returns_profile(self):
        UserProfile.objects.create(cognito_sub="me-sub", email="me@example.com", name="Me")
        session = self.client.session
        session["cognito_sub"] = "me-sub"
        session.save()
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "me@example.com")
