"""
Permission-based RBAC: check Permission by code for the current user's role.
Use require_permission('permission_code') after auth_required on API views.
Superuser bypasses permission check (has all). Customer routes use customer_auth_required, not this.
"""
from functools import wraps

from django.http import JsonResponse

from core.utils import get_role


def get_user_permission_codes(user):
    """
    Return set of permission codes for the given user.
    Resolves role from get_role(user), then Role -> RolePermission -> Permission codes.
    Superuser returns None (treated as "all permissions" in require_permission).
    """
    if not user or not getattr(user, 'is_authenticated', True):
        return set()
    if getattr(user, 'is_superuser', False):
        return None  # None = allow all in decorator
    from core.models import Role, RolePermission
    role_code = get_role(user)
    if not role_code:
        return set()
    try:
        role = Role.objects.get(code=role_code)
    except Role.DoesNotExist:
        return set()
    codes = set(
        RolePermission.objects.filter(role=role)
        .values_list('permission__code', flat=True)
    )
    return codes


def require_permission(permission_code):
    """
    Decorator: after auth, require that the user's role has the given permission.
    Use after auth_required. Superuser bypasses. Returns 403 if permission missing.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = getattr(request, 'user', None)
            if not user:
                return JsonResponse({'detail': 'Authentication required'}, status=401)
            codes = get_user_permission_codes(user)
            if codes is None:
                return view_func(request, *args, **kwargs)  # superuser
            if permission_code not in codes:
                return JsonResponse(
                    {'detail': 'You do not have permission to perform this action'},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
