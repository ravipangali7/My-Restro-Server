from rest_framework import permissions


class IsSuperuser(permissions.BasePermission):
    """Only superuser can access."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser
