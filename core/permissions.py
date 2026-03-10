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


class IsCustomer(permissions.BasePermission):
    """Only users with a customer profile can access. Use with _current_customer() for data scoping."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return hasattr(request.user, 'customer_profile') and request.user.customer_profile is not None
