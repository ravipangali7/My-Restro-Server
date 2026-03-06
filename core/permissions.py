from rest_framework import permissions


class IsSuperuser(permissions.BasePermission):
    """Only superuser can access."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


class IsSuperuserOrOwner(permissions.BasePermission):
    """Superuser, owner, or restaurant staff (e.g. manager) can access; views scope by _owner_or_manager_restaurant_ids."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_superuser
                or getattr(request.user, 'is_owner', False)
                or getattr(request.user, 'is_restaurant_staff', False)
            )
        )
