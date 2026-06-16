import secrets
from django.contrib.auth import logout as django_logout
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .cognito import build_authorize_url, exchange_code, build_logout_url


@api_view(["GET"])
def login(request):
    state = secrets.token_urlsafe(32)
    request.session["cognito_state"] = state
    return redirect(build_authorize_url(settings.COGNITO, state))


@api_view(["GET"])
def callback(request):
    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    expected_state = request.session.pop("cognito_state", None)

    if not expected_state or state != expected_state:
        return Response({"error": "Invalid state parameter"}, status=400)

    if not code:
        return Response({"error": "Missing authorization code"}, status=400)

    tokens = exchange_code(settings.COGNITO, code)
    if tokens is None:
        return Response({"error": "Token exchange failed"}, status=401)

    request.session["id_token"] = tokens.get("id_token", "")
    request.session["access_token"] = tokens.get("access_token", "")
    request.session["refresh_token"] = tokens.get("refresh_token", "")
    return redirect("/")


@api_view(["POST"])
def logout(request):
    django_logout(request)
    return redirect(build_logout_url(settings.COGNITO))
