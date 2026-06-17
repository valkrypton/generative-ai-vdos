import secrets
from datetime import datetime, timezone
from django.contrib.auth import logout as django_logout
from django.conf import settings
from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .cognito import build_authorize_url, exchange_code, build_logout_url, decode_id_token
from .serializers import UserProfileSerializer
from .services import CognitoService


@api_view(["GET"])
def login(request):
    state = secrets.token_urlsafe(32)
    request.session["cognito_state"] = state
    request.session.save()
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

    id_token = tokens.get("id_token", "")
    try:
        claims = decode_id_token(id_token)
    except Exception:
        return Response({"error": "Invalid ID token"}, status=401)

    sub = claims.get("sub")
    if not sub:
        return Response({"error": "ID token missing subject"}, status=401)

    CognitoService.get_or_create_profile(claims)

    # Rotate the session key on login to prevent session fixation.
    request.session.cycle_key()

    exp = claims.get("exp")
    if exp:
        expiry = datetime.fromtimestamp(exp, tz=timezone.utc)
        request.session.set_expiry(expiry)

    request.session["id_token"] = id_token
    request.session["access_token"] = tokens.get("access_token", "")
    request.session["refresh_token"] = tokens.get("refresh_token", "")
    request.session["cognito_sub"] = sub

    return redirect(f"{settings.FRONTEND_URL}/home")


@api_view(["GET", "POST"])
def logout(request):
    django_logout(request)
    return redirect(build_logout_url(settings.COGNITO))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserProfileSerializer(request.user).data)
