from django.db import models


class TimestampMixin(models.Model):
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Provider(TimestampMixin):
    code      = models.CharField(max_length=30, unique=True)
    name      = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
