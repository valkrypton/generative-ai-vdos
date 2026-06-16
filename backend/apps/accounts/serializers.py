from rest_framework import serializers
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["id", "cognito_sub", "email", "name", "created_at", "updated_at"]
        read_only_fields = ["id", "cognito_sub", "created_at", "updated_at"]
