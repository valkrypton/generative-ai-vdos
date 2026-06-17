from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, SceneViewSet

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")

urlpatterns = router.urls + [
    path(
        "projects/<uuid:project_pk>/scenes/",
        SceneViewSet.as_view({"get": "list"}),
        name="project-scenes-list",
    ),
    path(
        "projects/<uuid:project_pk>/scenes/<int:pk>/",
        SceneViewSet.as_view({"get": "retrieve"}),
        name="project-scenes-detail",
    ),
]
