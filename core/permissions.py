from rest_framework import permissions


class IsSuperuser(permissions.BasePermission):
    """Only superuser can access."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class IsSuperuserOrOwner(permissions.BasePermission):
    """Superuser or owner can access (owner gets scoped data)."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or getattr(request.user, 'is_owner', False))
        )
