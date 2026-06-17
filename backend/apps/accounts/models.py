from django.db import models
from apps.core.models import TimestampMixin


class UserProfile(TimestampMixin):
    cognito_sub = models.CharField(max_length=128, unique=True)
    email = models.EmailField(max_length=254)
    name = models.CharField(max_length=200, blank=True, default="")

    @property
    def is_authenticated(self):
        # Lets DRF's IsAuthenticated treat a resolved profile as a logged-in user.
        return True

    def __str__(self):
        return self.email
