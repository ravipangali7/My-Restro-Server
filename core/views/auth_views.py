"""
Function-based auth views: login, logout, staff profile, change password.
Unified login: tries User (staff) first, then Customer; one route for all roles.
"""
import json
import secrets
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import check_password
from rest_framework.authtoken.models import Token
from core.models import User, Customer, CustomerToken
from core.utils import get_restaurant_ids, get_role, auth_required, image_url_for_request
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code
from core.views.customer.auth_views import _phone_lookup_variants, _customer_to_dict


def _user_to_dict(user):
    if not user:
        return None
    role = get_role(user)
    restaurant_ids = []
    if role == 'super_admin':
        from core.models import Restaurant
        restaurant_ids = list(Restaurant.objects.values_list('id', flat=True))
    elif role == 'owner':
        restaurant_ids = list(
            user.restaurants.values_list('id', flat=True)
        )
    elif role in ('manager', 'waiter', 'kitchen'):
        from core.models import Staff
        restaurant_ids = list(
            Staff.objects.filter(user=user).values_list('restaurant_id', flat=True).distinct()
        )
    is_customer = (role == 'customer')
    return {
        'id': user.id,
        'name': user.name or getattr(user, 'username', ''),
        'phone': user.phone or '',
        'email': getattr(user, 'email', '') or '',
        'role': role,
        'restaurant_ids': restaurant_ids,
        'is_owner': getattr(user, 'is_owner', False),
        'is_restaurant_staff': getattr(user, 'is_restaurant_staff', False),
        'is_customer': is_customer,
        'kyc_status': getattr(user, 'kyc_status', ''),
        'is_shareholder': getattr(user, 'is_shareholder', False),
        'share_percentage': str(getattr(user, 'share_percentage', 0) or 0),
        'is_active': getattr(user, 'is_active', True),
    }


LOGIN_ERROR_MSG = 'Invalid country code or phone number.'


@csrf_exempt
@require_http_methods(['POST'])
def login(request):
    """
    Unified login: POST JSON { "phone", "password", "country_code" (required), optional "account_type" }.
    account_type: "customer" = try only Customer; "staff" or "user" = try only User; else try Customer first then User.
    Returns { "token", "user" } or { "token", "customer" } or 401.

    Deployment: Ensure the reverse proxy (nginx, Cloudflare, etc.) does NOT require authentication
    for this path. If the proxy returns 401 for unauthenticated requests, login will always fail.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    raw_phone = (body.get('phone') or '').strip().replace(' ', '')
    password = body.get('password', '')
    country_code = normalize_country_code((body.get('country_code') or '').strip())
    account_type = (body.get('account_type') or '').strip().lower()
    if not raw_phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
        }, status=400)
    if not password:
        return JsonResponse({'error': 'password required'}, status=400)

    try_customer_only = (account_type == 'customer')
    try_staff_only = (account_type in ('staff', 'user'))

    # 1) Try Customer: match by (country_code, phone) exactly
    if not try_staff_only:
        from core.views.customer.auth_views import _phone_for_storage
        phone_for_lookup = _phone_for_storage(raw_phone) if raw_phone else ''
        customer = Customer.objects.filter(
            country_code=country_code,
            phone=phone_for_lookup,
        ).first()
        if customer and customer.password and customer.password != '!' and check_password(password, customer.password):
            token, _ = CustomerToken.objects.get_or_create(
                customer=customer,
                defaults={'key': secrets.token_urlsafe(48)},
            )
            if not _:
                token.key = secrets.token_urlsafe(48)
                token.save(update_fields=['key'])
            return JsonResponse({
                'token': token.key,
                'customer': _customer_to_dict(customer),
            })
        if try_customer_only:
            return JsonResponse({'error': LOGIN_ERROR_MSG}, status=401)

    # 2) Try User (staff): match by (country_code, phone) exactly; no fallback
    if not try_customer_only:
        user = User.objects.filter(phone=raw_phone, country_code=country_code).first()
        if user and user.check_password(password):
            if not user.is_active:
                return JsonResponse({'error': 'Account disabled'}, status=403)
            token, _ = Token.objects.get_or_create(user=user)
            return JsonResponse({
                'token': token.key,
                'user': _user_to_dict(user),
            })
        if try_staff_only:
            return JsonResponse({'error': LOGIN_ERROR_MSG}, status=401)

    return JsonResponse({'error': LOGIN_ERROR_MSG}, status=401)


@csrf_exempt
@require_http_methods(['POST'])
def logout(request):
    """Invalidate token if using Token auth (delete token)."""
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if auth_header and auth_header.startswith('Bearer '):
        key = auth_header[7:].strip()
        from rest_framework.authtoken.models import Token
        Token.objects.filter(key=key).delete()
    return JsonResponse({'success': True})


def _staff_profile_to_dict(user, request=None):
    """Profile fields for GET/PATCH auth/profile (staff only). Includes kyc_status and share_percentage for owner."""
    try:
        out = {
            'id': getattr(user, 'id', getattr(user, 'pk', 0)),
            'name': getattr(user, 'name', '') or getattr(user, 'username', '') or '',
            'country_code': getattr(user, 'country_code', '') or '',
            'phone': getattr(user, 'phone', '') or '',
            'image': image_url_for_request(request, getattr(user, 'image', None)),
        }
        if getattr(user, 'is_owner', False):
            out['kyc_status'] = getattr(user, 'kyc_status', 'pending')
            out['is_shareholder'] = getattr(user, 'is_shareholder', False)
            out['share_percentage'] = str(getattr(user, 'share_percentage', 0) or 0)
        return out
    except Exception:
        return {
            'id': getattr(user, 'id', getattr(user, 'pk', 0)),
            'name': getattr(user, 'name', ''),
            'country_code': getattr(user, 'country_code', ''),
            'phone': getattr(user, 'phone', ''),
            'image': None,
        }


def _get_profile_body(request):
    """Parse PATCH body from form or JSON. Returns (dict, image_file)."""
    if request.POST or request.FILES:
        body = dict(request.POST.items()) if request.POST else {}
        for k, v in body.items():
            if isinstance(v, list) and len(v) == 1:
                body[k] = v[0]
        return body, request.FILES.get('image') if request.FILES else None
    content_type = (request.META.get('CONTENT_TYPE') or '').lower()
    if 'application/json' in content_type and request.body:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = {}
    else:
        body = {}
    return body, None


@auth_required
@require_http_methods(['GET'])
def staff_profile_get(request):
    """GET /api/auth/profile/ - current staff user profile (name, country_code, phone, image)."""
    user = request.user
    # Staff only (User with token); customer uses customer profile
    return JsonResponse(_staff_profile_to_dict(user, request))


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def staff_profile_patch(request):
    """PATCH /api/auth/profile/ - update current staff profile. Accepts JSON or multipart (image)."""
    user = request.user
    body, image_file = _get_profile_body(request)
    if image_file:
        user.image = image_file
    if 'name' in body:
        user.name = str(body['name']).strip()
    if 'phone' in body:
        new_phone = str(body['phone']).strip()
        if new_phone:
            new_cc = normalize_country_code(str(body.get('country_code') or user.country_code or '').strip())
            if User.objects.filter(country_code=new_cc, phone=new_phone).exclude(pk=user.pk).exists():
                return JsonResponse({'error': 'Another user with this country code and phone already exists'}, status=400)
        user.phone = new_phone
    if 'country_code' in body:
        new_cc = normalize_country_code(str(body['country_code']).strip())
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
            }, status=400)
        user.country_code = new_cc
    user.save()
    return JsonResponse(_staff_profile_to_dict(user, request))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def staff_change_password(request):
    """POST /api/auth/change-password/ - current_password, new_password (staff only)."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    current_password = body.get('current_password', '')
    new_password = body.get('new_password', '')
    if not current_password:
        return JsonResponse({'error': 'current_password required'}, status=400)
    if not new_password:
        return JsonResponse({'error': 'new_password required'}, status=400)
    if len(new_password) < 6:
        return JsonResponse({'error': 'new_password must be at least 6 characters'}, status=400)
    user = request.user
    if not user.check_password(current_password):
        return JsonResponse({'error': 'Current password is incorrect'}, status=400)
    user.set_password(new_password)
    user.save()
    return JsonResponse({'success': True})
