"""
Menu/permissions endpoint: returns allowed paths and has_* flags for the current user/customer.
Used by frontend to drive sidebar and bottom nav visibility (no manual refresh).
"""
from django.http import JsonResponse
from rest_framework.authtoken.models import Token

from core.models import Restaurant, User, QrStandOrder, CustomerToken
from core.utils import get_role


# Path lists per role (must match frontend sidebarConfigs)
SUPER_ADMIN_PATHS = [
    '/dashboard', '/restaurants', '/owners', '/kyc', '/finance',
    '/transaction-history', '/shareholders', '/share-distribution', '/withdrawals', '/qr-orders', '/reports', '/super-settings', '/settings',
]
OWNER_FULL_PATHS = [
    '/dashboard', '/orders', '/qr', '/qr-orders', '/menu', '/categories', '/units',
    '/combos', '/recipes', '/inventory', '/vendors', '/purchases', '/staff',
    '/staff-leaderboard', '/customers', '/analytics', '/pl-report', '/restaurants', '/transaction-history', '/settings',
]
OWNER_RESTRICTED_PATHS = [
    '/dashboard', '/live-orders', '/reports', '/analytics', '/pl-report', '/restaurants', '/staff', '/payments', '/transaction-history', '/settings',
]
MANAGER_PATHS = [
    '/dashboard', '/orders', '/qr', '/qr-orders', '/tables', '/order-menu', '/menu', '/categories', '/units',
    '/combos', '/recipes', '/inventory', '/vendors', '/purchases', '/stock-logs', '/staff',
    '/staff-leaderboard', '/attendance', '/customers', '/feedback', '/expenses',
    '/finance-records', '/pl-report', '/transaction-history', '/notifications', '/analytics', '/restaurants', '/settings',
]
WAITER_PATHS = [
    '/dashboard', '/restaurants', '/qr', '/tables', '/order-menu', '/new-orders', '/orders', '/qr-orders', '/transaction-history', '/call-waiter', '/feedback', '/settings',
]
KITCHEN_PATHS = ['/dashboard', '/kitchen-dashboard']
CUSTOMER_PATHS = [
    '/dashboard', '/restaurants', '/orders', '/transaction-history', '/feedback', '/pending-payments', '/profile', '/change-password',
]


def _filter_paths_by_has(paths, has_restaurants, has_shareholders, has_qr_orders):
    """Remove paths for modules that have no data (so sidebar hides them)."""
    out = []
    for p in paths:
        # Always show /shareholders for super_admin so they can add the first one
        if p == '/qr-orders' and not has_qr_orders:
            continue
        if p in ('/restaurants', '/owners') and not has_restaurants:
            continue
        out.append(p)
    return out


def _staff_menu(request):
    """Build menu for staff (User). request.user is set. Safe fallbacks to avoid 500."""
    user = getattr(request, 'user', None)
    if not user:
        return {
            'role': 'owner',
            'paths': list(OWNER_FULL_PATHS),
            'has_restaurants': False,
            'has_shareholders': False,
            'has_qr_orders': False,
        }
    role = get_role(user)
    if role is None:
        role = 'owner'
    try:
        if role == 'super_admin':
            has_restaurants = True
            has_shareholders = User.objects.filter(is_shareholder=True).exists()
            has_qr_orders = QrStandOrder.objects.exists()
            paths = _filter_paths_by_has(SUPER_ADMIN_PATHS, has_restaurants, has_shareholders, has_qr_orders)
        elif role == 'owner':
            if (
                getattr(user, 'is_owner', False)
                and getattr(user, 'kyc_status', '') == 'approved'
                and getattr(user, 'is_active', True)
            ):
                paths = list(OWNER_RESTRICTED_PATHS)
            else:
                paths = list(OWNER_FULL_PATHS)
            has_restaurants = Restaurant.objects.filter(user=user).exists()
            has_shareholders = False
            has_qr_orders = QrStandOrder.objects.filter(restaurant__user=user).exists()
            paths = _filter_paths_by_has(paths, has_restaurants, has_shareholders, has_qr_orders)
        elif role == 'manager':
            has_restaurants = True
            has_shareholders = False
            has_qr_orders = QrStandOrder.objects.filter(restaurant__staff__user=user).exists()
            paths = _filter_paths_by_has(MANAGER_PATHS, has_restaurants, has_shareholders, has_qr_orders)
        elif role == 'waiter':
            has_restaurants = True
            has_shareholders = False
            has_qr_orders = QrStandOrder.objects.filter(restaurant__staff__user=user).exists()
            paths = _filter_paths_by_has(WAITER_PATHS, has_restaurants, has_shareholders, has_qr_orders)
        elif role == 'kitchen':
            has_restaurants = True
            has_shareholders = False
            has_qr_orders = False
            paths = list(KITCHEN_PATHS)
        else:
            has_restaurants = Restaurant.objects.filter(user=user).exists()
            has_shareholders = False
            has_qr_orders = QrStandOrder.objects.filter(restaurant__user=user).exists()
            paths = _filter_paths_by_has(OWNER_FULL_PATHS, has_restaurants, has_shareholders, has_qr_orders)
        return {
            'role': role or 'owner',
            'paths': paths,
            'has_restaurants': has_restaurants,
            'has_shareholders': has_shareholders,
            'has_qr_orders': has_qr_orders,
        }
    except Exception:
        return {
            'role': role or 'owner',
            'paths': list(OWNER_FULL_PATHS),
            'has_restaurants': False,
            'has_shareholders': False,
            'has_qr_orders': False,
        }


def _customer_menu(request):
    """Build menu for customer. request.customer is set."""
    return {
        'role': 'customer',
        'paths': list(CUSTOMER_PATHS),
        'has_restaurants': True,
        'has_shareholders': False,
        'has_qr_orders': True,
    }


def menu_view(request):
    """
    GET /auth/menu/ — Returns { role, paths, has_restaurants, has_shareholders, has_qr_orders }.
    Tries DRF Token (staff) first, then CustomerToken (customer). Requires Bearer token.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if not auth_header or not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Authentication required'}, status=401)

    key = auth_header[7:].strip()

    # Try staff token first
    try:
        token = Token.objects.select_related('user').get(key=key)
        request.user = token.user
        try:
            data = _staff_menu(request)
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse(
                {'error': 'Menu error', 'detail': str(e)},
                status=500,
            )
    except Token.DoesNotExist:
        pass

    # Try customer token
    try:
        token = CustomerToken.objects.select_related('customer').get(key=key)
        request.customer = token.customer
        data = _customer_menu(request)
        return JsonResponse(data)
    except CustomerToken.DoesNotExist:
        pass

    return JsonResponse({'error': 'Invalid token'}, status=401)
