from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Project, Scene, JobLog
from .serializers import ProjectSerializer, ProjectCreateSerializer, SceneSerializer, JobLogSerializer
from .services import ProjectService


class ProjectViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return (
            Project.objects.filter(owner=self.request.user)
            .prefetch_related("scenes")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ProjectCreateSerializer
        return ProjectSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = ProjectService.create(owner=request.user, **serializer.validated_data)
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        project = self.get_object()
        logs = JobLog.objects.filter(project=project)
        return Response(JobLogSerializer(logs, many=True).data)


class SceneViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SceneSerializer

    def get_queryset(self):
        return Scene.objects.filter(
            project_id=self.kwargs["project_pk"],
            project__owner=self.request.user,
        )
