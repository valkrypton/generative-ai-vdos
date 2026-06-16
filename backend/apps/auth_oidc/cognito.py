import os
import urllib.parse
import requests
from django.core.exceptions import ImproperlyConfigured

_REQUIRED_VARS = (
    "COGNITO_DOMAIN",
    "COGNITO_APP_CLIENT_ID",
    "COGNITO_APP_CLIENT_SECRET",
    "COGNITO_REDIRECT_URI",
    "COGNITO_LOGOUT_REDIRECT_URI",
)


def get_config():
    config = {k: os.environ.get(k, "") for k in _REQUIRED_VARS}
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise ImproperlyConfigured(f"Missing COGNITO env vars: {', '.join(missing)}")
    return config


def build_authorize_url(config, state):
    params = {
        "response_type": "code",
        "client_id": config["COGNITO_APP_CLIENT_ID"],
        "redirect_uri": config["COGNITO_REDIRECT_URI"],
        "scope": "openid email profile",
        "state": state,
    }
    return f"{config['COGNITO_DOMAIN']}/oauth2/authorize?{urllib.parse.urlencode(params)}"


def exchange_code(config, code):
    resp = requests.post(
        f"{config['COGNITO_DOMAIN']}/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": config["COGNITO_APP_CLIENT_ID"],
            "client_secret": config["COGNITO_APP_CLIENT_SECRET"],
            "redirect_uri": config["COGNITO_REDIRECT_URI"],
            "code": code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if not resp.ok:
        return None
    return resp.json()


def build_logout_url(config):
    params = {
        "client_id": config["COGNITO_APP_CLIENT_ID"],
        "logout_uri": config["COGNITO_LOGOUT_REDIRECT_URI"],
    }
    return f"{config['COGNITO_DOMAIN']}/logout?{urllib.parse.urlencode(params)}"
