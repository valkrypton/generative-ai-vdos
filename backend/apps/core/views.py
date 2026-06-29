from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Provider


@api_view(["GET"])
@permission_classes([AllowAny])
def provider_list(request):
    providers = Provider.objects.filter(is_active=True).values("id", "code", "name")
    return Response(list(providers))
