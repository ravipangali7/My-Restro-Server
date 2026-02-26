"""Super Admin shareholders list, create, update. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from core.models import SuperSetting, ShareholderWithdrawal, Transaction, TransactionCategory
from core.utils import auth_required

User = get_user_model()


def _get_request_body(request):
    """Parse body from POST form or JSON. Returns (dict, image_file). Never reads request.body when POST/FILES present."""
    if request.POST or request.FILES:
        body = dict(request.POST.items()) if request.POST else {}
        for k, v in body.items():
            if isinstance(v, list) and len(v) == 1:
                body[k] = v[0]
        return body, request.FILES.get('image') if request.FILES else None
    content_type = (request.META.get('CONTENT_TYPE') or getattr(request, 'content_type', None) or '').lower()
    if 'application/json' in content_type and request.body:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = {}
    else:
        body = {}
    return body, None


def _shareholder_to_dict(u):
    return {
        'id': u.id,
        'name': getattr(u, 'name', '') or getattr(u, 'username', ''),
        'phone': getattr(u, 'phone', ''),
        'country_code': getattr(u, 'country_code', '') or '',
        'image': u.image.url if getattr(u, 'image', None) and u.image else None,
        'is_shareholder': getattr(u, 'is_shareholder', False),
        'share_percentage': str(getattr(u, 'share_percentage', 0) or 0),
        'balance': str(getattr(u, 'balance', 0) or 0),
        'due_balance': str(getattr(u, 'due_balance', 0) or 0),
    }


@auth_required
@require_http_methods(['GET'])
def super_admin_shareholder_detail(request, pk):
    u = get_object_or_404(User, pk=pk, is_shareholder=True)
    data = _shareholder_to_dict(u)
    # Withdrawals for this shareholder
    withdrawals_qs = ShareholderWithdrawal.objects.filter(user=u).order_by('-created_at')
    data['withdrawals'] = [
        {
            'id': w.id,
            'amount': str(w.amount),
            'status': w.status,
            'created_at': w.created_at.isoformat() if w.created_at else None,
        }
        for w in withdrawals_qs
    ]
    # Recent system-wide share distributions (last 20)
    dist_qs = (
        Transaction.objects.filter(is_system=True, category=TransactionCategory.SHARE_DISTRIBUTION)
        .order_by('-created_at')[:20]
    )
    data['recent_distributions'] = [
        {
            'date': t.created_at.isoformat() if t.created_at else None,
            'total_amount': str(t.amount),
        }
        for t in dist_qs
    ]
    return JsonResponse(data)


@require_http_methods(['GET'])
def super_admin_shareholder_list(request):
    qs = User.objects.filter(is_shareholder=True).order_by('username')
    total = qs.count()
    total_pct = sum(float(getattr(u, 'share_percentage', 0) or 0) for u in qs)
    system_balance = '0'
    try:
        ss = SuperSetting.objects.first()
        if ss:
            system_balance = str(ss.balance)
    except Exception:
        pass
    shareholder_balance = sum(Decimal(str(getattr(u, 'balance', 0) or 0)) for u in qs)
    stats = {
        'total': total,
        'total_percentage': round(total_pct, 2),
        'system_balance': system_balance,
        'shareholder_balance': str(shareholder_balance),
    }
    results = [_shareholder_to_dict(u) for u in qs]
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_shareholder_create(request):
    body, image_file = _get_request_body(request)
    phone = (body.get('phone') or '').strip()
    name = (body.get('name') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    user, _ = User.objects.get_or_create(phone=phone, defaults={'username': phone, 'name': name})
    user.is_shareholder = True
    user.share_percentage = Decimal(str(body.get('share_percentage', 0)))
    user.name = name or user.name
    country_code = (body.get('country_code') or '').strip()
    if country_code:
        user.country_code = country_code
    if image_file:
        user.image = image_file
    user.save()
    return JsonResponse(_shareholder_to_dict(user), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def super_admin_shareholder_update(request, pk):
    u = get_object_or_404(User, pk=pk)
    body, image_file = _get_request_body(request)
    if image_file:
        u.image = image_file
    if 'name' in body:
        u.name = str(body['name']).strip()
    if 'phone' in body:
        u.phone = str(body['phone']).strip()
    if 'share_percentage' in body:
        u.share_percentage = Decimal(str(body['share_percentage']))
    if 'country_code' in body:
        u.country_code = str(body.get('country_code', '')).strip()
    if 'is_shareholder' in body:
        u.is_shareholder = str(body.get('is_shareholder')).lower() in ('true', '1', 'yes')
    u.save()
    return JsonResponse(_shareholder_to_dict(u))
