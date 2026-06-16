from rest_framework.authentication import BaseAuthentication
from .models import UserProfile


class CognitoSessionAuthentication(BaseAuthentication):
    """Resolve the session's cognito_sub to a UserProfile and set request.user.

    Returns None (anonymous) when there is no session sub or no matching
    profile — combined with IsAuthenticated this yields a 401/403 rather than
    silently leaking data.
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
