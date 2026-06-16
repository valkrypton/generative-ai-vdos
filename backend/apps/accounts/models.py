from django.db import models
from apps.core.models import TimestampMixin


class UserProfile(TimestampMixin):
    cognito_sub = models.CharField(max_length=128, unique=True)
    email = models.EmailField(max_length=254)
    name = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return self.email
