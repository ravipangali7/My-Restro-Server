"""
Customer auth: register, login, logout, change-password, reset (OTP).
Separate from User auth; uses Customer model and CustomerToken only.
"""
import json
import re
import secrets
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
from django.core.cache import cache

from core.models import Customer, CustomerToken, User
from core.utils import customer_auth_required
from core.constants import ALLOWED_COUNTRY_CODES


def _normalize_phone(phone):
    if not phone:
        return ''
    return re.sub(r'\s+', '', str(phone).strip())


def _phone_lookup_variants(phone):
    """Return list of phone variants to try for Customer lookup (exact, then without country code)."""
    if not phone:
        return []
    normalized = re.sub(r'^\+', '', _normalize_phone(phone))
    if not normalized:
        return []
    variants = [normalized]
    # India: 91 + 10 digits -> try without 91
    if len(normalized) == 12 and normalized.startswith('91'):
        variants.append(normalized[2:])
    # Nepal: 977 + 10 digits -> try without 977
    if len(normalized) == 13 and normalized.startswith('977'):
        variants.append(normalized[3:])
    return variants


def _phone_for_storage(phone):
    """Return canonical phone for storage (prefer without country code to avoid duplicates)."""
    variants = _phone_lookup_variants(phone)
    return variants[-1] if len(variants) > 1 else (variants[0] if variants else '')


def _customer_to_dict(c):
    if not c:
        return None
    return {
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'country_code': c.country_code or '',
        'address': c.address or '',
        'fcm_token': getattr(c, 'fcm_token', '') or '',
    }


def _validate_password(password):
    if len(password) < 8:
        return 'Password must be at least 8 characters'
    return None


# --- Register (no auth) ---
@csrf_exempt
@require_http_methods(['POST'])
def customer_register(request):
    """
    POST JSON: name, phone, country_code (required), address, password, fcm_token (optional).
    If (country_code, phone) already exists: 400 "Phone already registered. Please login."
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    name = (body.get('name') or '').strip()
    raw_phone = _normalize_phone(body.get('phone'))
    phone = _phone_for_storage(raw_phone) if raw_phone else ''
    country_code = (body.get('country_code') or '').strip()
    address = (body.get('address') or '').strip()
    password = body.get('password', '')
    fcm_token = (body.get('fcm_token') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
        }, status=400)
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    err = _validate_password(password)
    if err:
        return JsonResponse({'error': err}, status=400)
    if Customer.objects.filter(country_code=country_code, phone=phone).exists():
        return JsonResponse(
            {'error': 'Phone already registered. Please login.'},
            status=400
        )
    user = None
    if not User.objects.filter(country_code=country_code, phone=phone).exists():
        user = User.objects.create(
            username=f'{country_code}_{phone}',  # unique for AbstractUser
            phone=phone,
            name=name,
            country_code=country_code,
        )
        user.set_password(password)
        user.save(update_fields=['password'])
    customer = Customer.objects.create(
        user=user,
        name=name,
        phone=phone,
        country_code=country_code,
        address=address,
        password=make_password(password),
        fcm_token=fcm_token or '',
    )
    token = CustomerToken.objects.create(
        customer=customer,
        key=secrets.token_urlsafe(48),
    )
    return JsonResponse({
        'token': token.key,
        'customer': _customer_to_dict(customer),
    })


# --- Login (no auth) ---
@csrf_exempt
@require_http_methods(['POST'])
def customer_login(request):
    """
    POST JSON: phone, password, fcm_token (optional).
    Uses Customer + CustomerToken only; no User/DRF Token.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    phone = _normalize_phone(body.get('phone'))
    password = body.get('password', '')
    fcm_token = (body.get('fcm_token') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not password:
        return JsonResponse({'error': 'password required'}, status=400)
    # Try exact normalized phone, then variants without country code (e.g. 91, 977)
    customer = None
    for variant in _phone_lookup_variants(phone):
        customer = Customer.objects.filter(phone=variant).first()
        if customer:
            break
    if not customer:
        return JsonResponse({'error': 'Invalid phone or password'}, status=401)
    if not customer.password or customer.password == '!':
        return JsonResponse(
            {'error': 'Account not set up for login. Please reset your password.'},
            status=403
        )
    if not check_password(password, customer.password):
        return JsonResponse({'error': 'Invalid phone or password'}, status=401)
    # Backfill User for dashboard login if not already linked (use customer.phone for consistency)
    cust_phone = customer.phone
    if customer.user_id is None and not User.objects.filter(phone=cust_phone).exists():
        user = User.objects.create(
            username=cust_phone,
            phone=cust_phone,
            name=customer.name,
            country_code=customer.country_code or '',
        )
        user.set_password(password)
        user.save(update_fields=['password'])
        customer.user = user
        customer.save(update_fields=['user', 'updated_at'])
    if fcm_token:
        customer.fcm_token = fcm_token
        customer.save(update_fields=['fcm_token', 'updated_at'])
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


# --- Logout (customer auth) ---
@csrf_exempt
@require_http_methods(['POST'])
@customer_auth_required
def customer_logout(request):
    """Delete the current customer token."""
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if auth_header and auth_header.startswith('Bearer '):
        key = auth_header[7:].strip()
        CustomerToken.objects.filter(key=key).delete()
    return JsonResponse({'success': True})


# --- Change password (customer auth) ---
@csrf_exempt
@require_http_methods(['POST'])
@customer_auth_required
def customer_change_password(request):
    """POST JSON: old_password, new_password."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    old_password = body.get('old_password', '')
    new_password = body.get('new_password', '')
    if not old_password:
        return JsonResponse({'error': 'old_password required'}, status=400)
    if not new_password:
        return JsonResponse({'error': 'new_password required'}, status=400)
    err = _validate_password(new_password)
    if err:
        return JsonResponse({'error': err}, status=400)
    customer = request.customer
    if not check_password(old_password, customer.password):
        return JsonResponse({'error': 'Current password is incorrect'}, status=400)
    customer.password = make_password(new_password)
    customer.save(update_fields=['password', 'updated_at'])
    return JsonResponse({'success': True})


# --- Request reset OTP (no auth), rate-limited by phone ---
OTP_CACHE_PREFIX = 'customer_otp:'
OTP_RATE_PREFIX = 'customer_otp_rate:'
OTP_TTL = 600  # 10 min
RATE_TTL = 60   # 1 min between requests per phone


@csrf_exempt
@require_http_methods(['POST'])
def customer_request_reset(request):
    """
    POST JSON: phone, country_code (required). Generate 6-digit OTP, store in cache, send (stub).
    Rate-limit: one request per (country_code, phone) per minute.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    raw_phone = _normalize_phone(body.get('phone'))
    phone = _phone_for_storage(raw_phone) if raw_phone else ''
    country_code = (body.get('country_code') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
        }, status=400)
    rate_key = OTP_RATE_PREFIX + country_code + '_' + phone
    if cache.get(rate_key):
        return JsonResponse(
            {'error': 'Please wait a minute before requesting another OTP'},
            status=429
        )
    customer = Customer.objects.filter(country_code=country_code, phone=phone).first()
    if not customer:
        return JsonResponse({'error': 'Invalid country code or phone number.'}, status=404)
    otp = ''.join(secrets.choice('0123456789') for _ in range(6))
    cache_key = OTP_CACHE_PREFIX + country_code + '_' + phone
    cache.set(cache_key, otp, timeout=OTP_TTL)
    cache.set(rate_key, '1', timeout=RATE_TTL)
    # TODO: send OTP via SMS when provider is configured
    return JsonResponse({'message': 'OTP sent'})


# --- Confirm reset (no auth) ---
@csrf_exempt
@require_http_methods(['POST'])
def customer_confirm_reset(request):
    """POST JSON: phone, country_code (required), otp, new_password. Verify OTP and set password."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    raw_phone = _normalize_phone(body.get('phone'))
    phone = _phone_for_storage(raw_phone) if raw_phone else ''
    country_code = (body.get('country_code') or '').strip()
    otp = (body.get('otp') or '').strip()
    new_password = body.get('new_password', '')
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
        }, status=400)
    if not otp:
        return JsonResponse({'error': 'otp required'}, status=400)
    if not new_password:
        return JsonResponse({'error': 'new_password required'}, status=400)
    err = _validate_password(new_password)
    if err:
        return JsonResponse({'error': err}, status=400)
    cache_key = OTP_CACHE_PREFIX + country_code + '_' + phone
    stored = cache.get(cache_key)
    if not stored or stored != otp:
        return JsonResponse({'error': 'Invalid or expired OTP'}, status=400)
    customer = Customer.objects.filter(country_code=country_code, phone=phone).first()
    if not customer:
        return JsonResponse({'error': 'Invalid country code or phone number.'}, status=404)
    customer.password = make_password(new_password)
    customer.save(update_fields=['password', 'updated_at'])
    cache.delete(cache_key)
    return JsonResponse({'success': True})
