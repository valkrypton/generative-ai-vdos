from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from apps.accounts.models import UserProfile
from .models import Project, Scene, JobLog
from .serializers import ProjectSerializer, ProjectCreateSerializer, SceneSerializer, JobLogSerializer
from .services import ProjectService


def _get_owner(request) -> UserProfile:
    sub = request.session.get("cognito_sub")
    if not sub:
        raise AuthenticationFailed("Not authenticated.")
    try:
        return UserProfile.objects.get(cognito_sub=sub)
    except UserProfile.DoesNotExist:
        raise AuthenticationFailed("User profile not found.")


class ProjectViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        sub = self.request.session.get("cognito_sub")
        if not sub:
            return Project.objects.none()
        return (
            Project.objects.filter(owner__cognito_sub=sub)
            .prefetch_related("scenes")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ProjectCreateSerializer
        return ProjectSerializer

    def create(self, request, *args, **kwargs):
        owner = _get_owner(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = ProjectService.create(owner=owner, **serializer.validated_data)
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        project = self.get_object()
        logs = JobLog.objects.filter(project=project)
        return Response(JobLogSerializer(logs, many=True).data)


class SceneViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SceneSerializer

    def get_queryset(self):
        return Scene.objects.filter(project_id=self.kwargs["project_pk"])
