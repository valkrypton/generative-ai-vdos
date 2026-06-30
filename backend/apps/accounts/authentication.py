from rest_framework.authentication import BaseAuthentication
from .models import UserProfile


class CognitoSessionAuthentication(BaseAuthentication):
    """Resolve the session's cognito_sub to a UserProfile and set request.user.

    Returns None (anonymous) when there is no session sub or no matching
    profile — combined with IsAuthenticated this yields a 401/403 rather than
    silently leaking data.

    CSRF posture (deliberate): unlike DRF's SessionAuthentication, this
    authenticator performs **no** CSRF token check, and Django's
    CsrfViewMiddleware is intentionally absent from MIDDLEWARE. Cross-site
    write protection relies solely on ``SESSION_COOKIE_SAMESITE = "Lax"``,
    which prevents the session cookie from riding along on cross-site
    POST/PATCH/DELETE requests. All first-party mutations originate from the
    Next.js same-origin rewrite proxy, so they are unaffected. If clients ever
    send credentials cross-origin (or Bearer tokens directly), add explicit
    CSRF token enforcement here.
    """

    def authenticate(self, request):
        sub = request.session.get("cognito_sub")
        if not sub:
            return None
        try:
            profile = UserProfile.objects.get(cognito_sub=sub)
        except UserProfile.DoesNotExist:
            return None
        return (profile, None)
