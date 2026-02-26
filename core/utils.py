"""
Shared helpers for API: model serialization (snake_case) and restaurant scope.
"""
from django.forms.models import model_to_dict as _model_to_dict
from decimal import Decimal
from datetime import date, datetime


def _serialize_value(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if hasattr(v, 'url') and callable(getattr(v, 'url', None)):
        return v.url if v else None
    if hasattr(v, 'pk'):
        return v.pk
    return v


def model_to_dict(instance, fields=None, exclude=None):
    """
    Return a dict of the model instance with snake_case keys and serializable values.
    FK and M2M become id(s). Decimals and dates become strings/isoformat.
    """
    if instance is None:
        return None
    raw = _model_to_dict(instance, fields=fields, exclude=exclude)
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[k] = {kk: _serialize_value(vv) for kk, vv in v.items()}
        elif isinstance(v, list):
            out[k] = [_serialize_value(x) for x in v]
        else:
            out[k] = _serialize_value(v)
    return out


def get_restaurant_ids(request):
    """
    Return list of restaurant IDs the current user can access.
    - Super admin (is_superuser): all restaurant IDs.
    - Owner (is_owner): restaurants owned by user.
    - Waiter (is_waiter): single restaurant from staff.restaurant (get_waiter_restaurant).
    - Manager (is_restaurant_staff): restaurants from Staff assignments.
    - Customer or anonymous: empty list (for global endpoints).
    """
    from core.models import Restaurant, Staff
    from core.permissions import get_waiter_restaurant, is_waiter

    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return []

    user = request.user
    if getattr(user, 'is_superuser', False):
        return list(Restaurant.objects.values_list('id', flat=True))
    if getattr(user, 'is_owner', False):
        return list(Restaurant.objects.filter(user=user).values_list('id', flat=True))
    if is_waiter(user):
        restaurant = get_waiter_restaurant(request)
        return [restaurant.id] if restaurant else []
    if getattr(user, 'is_restaurant_staff', False):
        return list(Staff.objects.filter(user=user).values_list('restaurant_id', flat=True).distinct())
    return []


def get_staff_id(request):
    """Return Staff pk for current user if they are restaurant staff (manager/waiter), else None."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    if not getattr(request.user, 'is_restaurant_staff', False):
        return None
    from core.models import Staff
    staff = Staff.objects.filter(user=request.user).first()
    return staff.pk if staff else None


def get_waiter_staff_id(request):
    """Return Staff pk for current user if they are a waiter (is_waiter=True), else None."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    if not getattr(request.user, 'is_restaurant_staff', False):
        return None
    from core.models import Staff
    staff = Staff.objects.filter(user=request.user, is_waiter=True).first()
    return staff.pk if staff else None


def get_customer_id(request):
    """Return Customer pk for current user (match by phone), else None."""
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    phone = getattr(request.user, 'phone', None)
    if not phone:
        return None
    from core.models import Customer
    c = Customer.objects.filter(phone=phone).first()
    return c.pk if c else None


def get_role(user):
    """Return role string: super_admin, owner, manager, waiter, kitchen, customer."""
    if not user or not getattr(user, 'is_authenticated', True):
        return None
    if getattr(user, 'is_superuser', False):
        return 'super_admin'
    if getattr(user, 'is_owner', False):
        return 'owner'
    if getattr(user, 'is_restaurant_staff', False):
        if getattr(user, 'is_kitchen', False):
            return 'kitchen'
        from core.models import Staff
        staff = Staff.objects.filter(user=user).first()
        if staff and getattr(staff, 'is_manager', False):
            return 'manager'
        if staff and getattr(staff, 'is_waiter', False):
            return 'waiter'
        return 'manager'  # fallback
    from core.models import Customer
    if Customer.objects.filter(user=user).exists():
        return 'customer'
    return 'owner'  # fallback so login response always has a role and dashboard can render


def is_owner_only(request):
    """
    True when the current user is an owner (is_owner=True) and not a superuser.
    Used for RBAC: owner-only users get restricted access (no operations/products/inventory/etc).
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return False
    return bool(getattr(request.user, 'is_owner', False)) and not bool(
        getattr(request.user, 'is_superuser', False)
    )


def owner_forbidden(view_func):
    """
    Decorator: if request.user is owner-only (is_owner, not superuser), return 403.
    Apply to owner API views that managers/superusers may use but owners must not.
    """
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if is_owner_only(request):
            return JsonResponse({'detail': 'Not allowed for Owner'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapped


def superuser_required(view_func):
    """Decorator: require request.user.is_superuser. Return 403 otherwise. Use after auth_required."""
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, 'is_superuser', False):
            return JsonResponse({'detail': 'Super admin only'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapped


def super_admin_required(view_func):
    """Decorator: auth required + superuser required. Use for all super_admin API views."""
    return auth_required(superuser_required(view_func))


def auth_required(view_func):
    """Decorator: set request.user from Authorization Bearer token (DRF Token only). Return 401 if invalid."""
    from functools import wraps
    from rest_framework.authtoken.models import Token

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            from django.http import JsonResponse
            return JsonResponse({'error': 'Authentication required'}, status=401)
        key = auth_header[7:].strip()
        try:
            token = Token.objects.select_related('user').get(key=key)
            request.user = token.user
        except Token.DoesNotExist:
            from django.http import JsonResponse
            return JsonResponse({'error': 'Invalid token'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapped


def customer_auth_required(view_func):
    """
    Decorator: set request.customer from Authorization Bearer token (CustomerToken only).
    Does not use DRF Token / User. Return 401 if missing or invalid.
    """
    from functools import wraps
    from django.http import JsonResponse
    from core.models import CustomerToken

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Authentication required'}, status=401)
        key = auth_header[7:].strip()
        try:
            token = CustomerToken.objects.select_related('customer').get(key=key)
            request.customer = token.customer
        except CustomerToken.DoesNotExist:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapped


def get_customer_id_from_request(request):
    """
    Return Customer pk when request.customer is set (by customer_auth_required). Else None.
    Use in customer API views only (after customer_auth_required).
    """
    customer = getattr(request, 'customer', None)
    return customer.id if customer else None
