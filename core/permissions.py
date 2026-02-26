"""
Manager and Waiter RBAC: permission helpers and decorators for role-based access control.
Manager: user.is_restaurant_staff and staff.is_manager; data scoped to staff.restaurant.
Waiter: user.is_restaurant_staff and staff.is_waiter; data scoped to staff.restaurant and waiter_id.
Owner: user.is_owner + is_active + kyc_status=approved; data scoped to user's restaurants.
"""
from functools import wraps
from django.http import JsonResponse


# --- Owner RBAC ---


def is_owner_eligible(user):
    """Return True iff user is owner with is_active=True and kyc_status=approved (dashboard access)."""
    if not user or not getattr(user, 'is_authenticated', True):
        return False
    if not getattr(user, 'is_owner', False):
        return False
    if not getattr(user, 'is_active', True):
        return False
    return getattr(user, 'kyc_status', '') == 'approved'


def owner_or_superuser_required(view_func):
    """
    Decorator: after auth, require request.user is superuser OR (is_owner and is_active)
    OR (user owns at least one restaurant and is_active). No KYC check.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if getattr(request.user, 'is_superuser', False):
            return view_func(request, *args, **kwargs)
        if not getattr(request.user, 'is_active', True):
            return JsonResponse(
                {'detail': 'Owner or superuser access required', 'locked': False},
                status=403,
            )
        if getattr(request.user, 'is_owner', False):
            return view_func(request, *args, **kwargs)
        from core.models import Restaurant
        if Restaurant.objects.filter(user=request.user).exists():
            return view_func(request, *args, **kwargs)
        return JsonResponse(
            {'detail': 'Owner or superuser access required', 'locked': False},
            status=403,
        )
    return wrapped


def owner_required(view_func):
    """
    Decorator: after auth, require request.user is owner with is_active=True and kyc_status=approved
    (dashboard-level access). Superuser is allowed to pass. Use only for dashboard, analytics, pl, payments.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if getattr(request.user, 'is_superuser', False):
            return view_func(request, *args, **kwargs)
        if not is_owner_eligible(request.user):
            return JsonResponse(
                {
                    'detail': 'Owner dashboard requires approved KYC and active account',
                    'locked': False,
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapped


def owner_unlocked(view_func):
    """
    Decorator: if user is owner (and not superuser), check that no restaurant they own has
    due_balance > SuperSetting.due_threshold. If any is over, return 403 with locked=True.
    Superuser and non-owners pass through.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if getattr(request.user, 'is_superuser', False) or not getattr(request.user, 'is_owner', False):
            return view_func(request, *args, **kwargs)
        from core.models import Restaurant, SuperSetting
        restaurant_ids = list(
            Restaurant.objects.filter(user=request.user).values_list('id', flat=True)
        )
        if not restaurant_ids:
            return view_func(request, *args, **kwargs)
        ss = SuperSetting.objects.first()
        threshold = (ss.due_threshold or 0) if ss else 0
        over = list(
            Restaurant.objects.filter(id__in=restaurant_ids).filter(
                due_balance__gt=threshold
            ).values_list('id', 'name', 'due_balance')
        )
        if over:
            return JsonResponse(
                {
                    'locked': True,
                    'detail': 'Please clear due balance first',
                    'restaurants_over': [
                        {'id': r[0], 'name': r[1], 'due_balance': str(r[2])}
                        for r in over
                    ],
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapped


# --- Manager RBAC ---


def is_manager(user):
    """Return True iff user is restaurant staff with is_manager=True."""
    if not user or not getattr(user, 'is_authenticated', True):
        return False
    if not getattr(user, 'is_restaurant_staff', False):
        return False
    from core.models import Staff
    return Staff.objects.filter(user=user, is_manager=True).exists()


def get_manager_restaurant(request):
    """
    If request.user is a manager, return their assigned Restaurant (first one).
    Else return None. Use for strict single-restaurant scoping.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    if not is_manager(request.user):
        return None
    from core.models import Staff
    staff = Staff.objects.filter(user=request.user, is_manager=True).select_related('restaurant').first()
    return staff.restaurant if staff else None


def manager_required(view_func):
    """
    Decorator: after auth, require that request.user is a manager.
    Return 403 with detail if not.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_manager(request.user):
            return JsonResponse(
                {'detail': 'Manager access required', 'locked': False},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapped


def manager_unlocked(view_func):
    """
    Decorator: if user is manager, check restaurant.due_balance <= SuperSetting.due_threshold.
    If over threshold, return 403 with locked=True so frontend can show "Please clear full due balance".
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_manager(request.user):
            return view_func(request, *args, **kwargs)
        restaurant = get_manager_restaurant(request)
        if not restaurant:
            return JsonResponse(
                {'detail': 'No restaurant assigned', 'locked': False},
                status=403
            )
        from core.models import SuperSetting
        ss = SuperSetting.objects.first()
        threshold = (ss.due_threshold or 0) if ss else 0
        if (restaurant.due_balance or 0) > threshold:
            return JsonResponse(
                {'locked': True, 'detail': 'Please clear full due balance'},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapped


# --- Kitchen RBAC ---


def is_kitchen(user):
    """Return True iff user has is_restaurant_staff and is_kitchen."""
    if not user or not getattr(user, 'is_authenticated', True):
        return False
    return bool(
        getattr(user, 'is_restaurant_staff', False) and getattr(user, 'is_kitchen', False)
    )


def kitchen_required(view_func):
    """
    Decorator: after auth, require that request.user is kitchen (is_restaurant_staff + is_kitchen).
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_kitchen(request.user):
            return JsonResponse(
                {'detail': 'Kitchen access required', 'locked': False},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapped


# --- Waiter RBAC ---


def is_waiter(user):
    """Return True iff user is restaurant staff with is_waiter=True."""
    if not user or not getattr(user, 'is_authenticated', True):
        return False
    if not getattr(user, 'is_restaurant_staff', False):
        return False
    from core.models import Staff
    return Staff.objects.filter(user=user, is_waiter=True).exists()


def get_waiter_restaurant(request):
    """
    If request.user is a waiter, return their assigned Restaurant (first one).
    Else return None. Use for strict single-restaurant scoping.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return None
    if not is_waiter(request.user):
        return None
    from core.models import Staff
    staff = Staff.objects.filter(user=request.user, is_waiter=True).select_related('restaurant').first()
    return staff.restaurant if staff else None


def waiter_required(view_func):
    """
    Decorator: after auth, require that request.user is a waiter.
    Return 403 with detail if not.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_waiter(request.user):
            return JsonResponse(
                {'detail': 'Waiter access required', 'locked': False},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapped


def waiter_unlocked(view_func):
    """
    Decorator: if user is waiter, check restaurant.due_balance <= SuperSetting.due_threshold.
    If over threshold, return 403 with locked=True so frontend can show
    "Restaurant due pending. Please contact manager."
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not is_waiter(request.user):
            return view_func(request, *args, **kwargs)
        restaurant = get_waiter_restaurant(request)
        if not restaurant:
            return JsonResponse(
                {'detail': 'No restaurant assigned', 'locked': False},
                status=403
            )
        from core.models import SuperSetting
        ss = SuperSetting.objects.first()
        threshold = (ss.due_threshold or 0) if ss else 0
        if (restaurant.due_balance or 0) > threshold:
            return JsonResponse(
                {'locked': True, 'detail': 'Restaurant due pending. Please contact manager.'},
                status=403
            )
        return view_func(request, *args, **kwargs)
    return wrapped
