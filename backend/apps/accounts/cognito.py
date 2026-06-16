import urllib.parse
import requests
from jose import jwt as jose_jwt


def decode_id_token(token: str) -> dict:
    return jose_jwt.get_unverified_claims(token)


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
