"""Super Admin only: request OTP for password reset, confirm reset with OTP + new password."""
import json
import random
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from core.utils import super_admin_required

OTP_CACHE_KEY_PREFIX = 'super_admin_reset_otp:'
OTP_TTL = 600  # 10 min


@csrf_exempt
@super_admin_required
@require_http_methods(['POST'])
def super_admin_request_password_reset(request):
    """
    POST (no body or empty). Generate 6-digit OTP, store in cache by request.user.id.
    Only Super Admin can call. In production, send OTP via SMS/email; for dev we return it.
    """
    user = request.user
    otp = ''.join(str(random.randint(0, 9)) for _ in range(6))
    cache_key = OTP_CACHE_KEY_PREFIX + str(user.id)
    cache.set(cache_key, otp, OTP_TTL)
    # TODO: send OTP via SMS/email to user.phone
    # For development, include otp in response (remove in production)
    return JsonResponse({
        'message': 'OTP sent to your registered phone.',
        'otp': otp,  # remove in production
    })


@csrf_exempt
@super_admin_required
@require_http_methods(['POST'])
def super_admin_confirm_password_reset(request):
    """POST JSON: otp, new_password. Verify OTP for request.user, set password, invalidate OTP."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    otp = (body.get('otp') or '').strip()
    new_password = body.get('new_password', '')
    if not otp:
        return JsonResponse({'error': 'otp required'}, status=400)
    if not new_password:
        return JsonResponse({'error': 'new_password required'}, status=400)
    if len(new_password) < 6:
        return JsonResponse({'error': 'new_password must be at least 6 characters'}, status=400)
    user = request.user
    cache_key = OTP_CACHE_KEY_PREFIX + str(user.id)
    stored = cache.get(cache_key)
    if not stored or stored != otp:
        return JsonResponse({'error': 'Invalid or expired OTP'}, status=400)
    cache.delete(cache_key)
    user.set_password(new_password)
    user.save()
    return JsonResponse({'success': True})
