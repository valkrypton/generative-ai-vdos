import secrets
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from .cognito import build_authorize_url, exchange_code, build_logout_url


def login(request):
    state = secrets.token_urlsafe(32)
    request.session["cognito_state"] = state
    return redirect(build_authorize_url(settings.COGNITO, state))


def callback(request):
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    expected_state = request.session.pop("cognito_state", None)

    if not expected_state or state != expected_state:
        return JsonResponse({"error": "Invalid state parameter"}, status=400)

    if not code:
        return JsonResponse({"error": "Missing authorization code"}, status=400)

    tokens = exchange_code(settings.COGNITO, code)
    if tokens is None:
        return JsonResponse({"error": "Token exchange failed"}, status=401)

    request.session["id_token"] = tokens.get("id_token", "")
    request.session["access_token"] = tokens.get("access_token", "")
    request.session["refresh_token"] = tokens.get("refresh_token", "")
    return redirect("/")


def logout(request):
    request.session.flush()
    return redirect(build_logout_url(settings.COGNITO))
