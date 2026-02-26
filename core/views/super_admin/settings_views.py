"""Super Admin system settings GET/PATCH single SuperSetting. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from core.models import SuperSetting
from core.utils import auth_required


def _setting_to_dict(s):
    if not s:
        return {}
    return {
        'id': s.id,
        'balance': str(s.balance),
        'per_transaction_fee': str(s.per_transaction_fee) if s.per_transaction_fee is not None else None,
        'subscription_fee_per_month': str(s.subscription_fee_per_month) if s.subscription_fee_per_month is not None else None,
        'per_qr_stand_price': str(s.per_qr_stand_price) if s.per_qr_stand_price is not None else None,
        'is_subscription_fee': s.is_subscription_fee,
        'due_threshold': str(s.due_threshold) if s.due_threshold is not None else None,
        'is_whatsapp_usgage': s.is_whatsapp_usgage,
        'whatsapp_per_usgage': str(s.whatsapp_per_usgage) if s.whatsapp_per_usgage is not None else None,
        'share_distribution_day': s.share_distribution_day,
        'ug_api': s.ug_api or '',
        'created_at': s.created_at.isoformat() if s.created_at else None,
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


@require_http_methods(['GET'])
def super_admin_settings_get(request):
    s = SuperSetting.objects.first()
    return JsonResponse(_setting_to_dict(s) or {})


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_settings_patch(request):
    s = SuperSetting.objects.first()
    if not s:
        s = SuperSetting.objects.create(balance=Decimal('0'))
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    for key in ('balance', 'per_transaction_fee', 'subscription_fee_per_month', 'per_qr_stand_price',
                'due_threshold', 'whatsapp_per_usgage', 'share_distribution_day'):
        if key in body and body[key] is not None:
            if key in ('share_distribution_day',):
                setattr(s, key, body[key])
            else:
                setattr(s, key, Decimal(str(body[key])))
    if 'is_subscription_fee' in body:
        s.is_subscription_fee = bool(body['is_subscription_fee'])
    if 'is_whatsapp_usgage' in body:
        s.is_whatsapp_usgage = bool(body['is_whatsapp_usgage'])
    if 'ug_api' in body:
        s.ug_api = str(body.get('ug_api', ''))
    s.save()
    return JsonResponse(_setting_to_dict(s))
