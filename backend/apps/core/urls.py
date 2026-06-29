from django.urls import path
from . import views

urlpatterns = [
    path("providers/", views.provider_list, name="provider-list"),
]
