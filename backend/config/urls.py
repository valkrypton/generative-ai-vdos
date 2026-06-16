from django.urls import path, include

urlpatterns = [
    path("api/", include("apps.health.urls")),
    path("api/auth/", include("apps.accounts.urls")),
]
