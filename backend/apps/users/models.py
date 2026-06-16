from django.db import models


class UserProfile(models.Model):
    cognito_sub = models.CharField(max_length=128, unique=True, db_index=True)
    email = models.CharField(max_length=254)
    name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
