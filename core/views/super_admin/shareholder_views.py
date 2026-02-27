"""Super Admin shareholders list, create, update. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from django.db.models import Sum, Q, Count
from core.models import SuperSetting, ShareholderWithdrawal, Transaction, TransactionCategory, WithdrawalStatus
from core.utils import auth_required, image_url_for_request, paginate_queryset, parse_date
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code

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


def _shareholder_to_dict(u, include_extra=False, request=None):
    d = {
        'id': u.id,
        'name': getattr(u, 'name', '') or getattr(u, 'username', ''),
        'phone': getattr(u, 'phone', ''),
        'country_code': getattr(u, 'country_code', '') or '',
        'email': getattr(u, 'email', '') or '',
        'image': image_url_for_request(request, getattr(u, 'image', None)),
        'is_shareholder': getattr(u, 'is_shareholder', False),
        'share_percentage': str(getattr(u, 'share_percentage', 0) or 0),
        'balance': str(getattr(u, 'balance', 0) or 0),
        'due_balance': str(getattr(u, 'due_balance', 0) or 0),
        'kyc_status': getattr(u, 'kyc_status', '') or 'pending',
        'kyc_document': image_url_for_request(request, getattr(u, 'kyc_document', None)),
        'created_at': u.created_at.isoformat() if getattr(u, 'created_at', None) and u.created_at else None,
    }
    return d


@auth_required
@require_http_methods(['GET'])
def super_admin_shareholder_detail(request, pk):
    u = get_object_or_404(User, pk=pk)
    data = _shareholder_to_dict(u, include_extra=True, request=request)
    # Withdrawals for this shareholder (single query, reuse for lists)
    withdrawals_qs = ShareholderWithdrawal.objects.filter(user=u).order_by('-created_at')
    withdrawals_list = list(withdrawals_qs)
    data['withdrawals'] = [
        {'id': w.id, 'amount': str(w.amount), 'status': w.status, 'created_at': w.created_at.isoformat() if w.created_at else None}
        for w in withdrawals_list
    ]
    # Financial summary from withdrawals (single aggregate to avoid N+1)
    agg = ShareholderWithdrawal.objects.filter(user=u).aggregate(
        total_withdrawn=Sum('amount', filter=Q(status=WithdrawalStatus.APPROVED)),
        pending_sum=Sum('amount', filter=Q(status=WithdrawalStatus.PENDING)),
        approved_sum=Sum('amount', filter=Q(status=WithdrawalStatus.APPROVED)),
        rejected_sum=Sum('amount', filter=Q(status=WithdrawalStatus.REJECT)),
        withdrawal_pending_count=Count('id', filter=Q(status=WithdrawalStatus.PENDING)),
        withdrawal_approved_count=Count('id', filter=Q(status=WithdrawalStatus.APPROVED)),
        withdrawal_rejected_count=Count('id', filter=Q(status=WithdrawalStatus.REJECT)),
    )
    total_withdrawn = agg['total_withdrawn'] or Decimal('0')
    data['total_withdrawn'] = str(total_withdrawn)
    data['withdrawal_pending_count'] = agg.get('withdrawal_pending_count') or 0
    data['withdrawal_approved_count'] = agg.get('withdrawal_approved_count') or 0
    data['withdrawal_rejected_count'] = agg.get('withdrawal_rejected_count') or 0
    data['withdrawal_pending_sum'] = str(agg['pending_sum'] or Decimal('0'))
    data['withdrawal_approved_sum'] = str(agg['approved_sum'] or Decimal('0'))
    data['withdrawal_rejected_sum'] = str(agg['rejected_sum'] or Decimal('0'))
    balance = Decimal(str(data['balance']))
    data['total_share_distributed'] = str(balance + total_withdrawn)
    data['net_profit_from_shares'] = data['balance']
    # Stats cards for detail page
    share_distribution_agg = Transaction.objects.filter(category=TransactionCategory.SHARE_DISTRIBUTION).aggregate(
        total_amount=Sum('amount'), count=Count('id')
    )
    data['stats'] = {
        'total_share_percentage': float(data.get('share_percentage', 0) or 0),
        'current_balance': data['balance'],
        'total_withdrawals': data['total_withdrawn'],
        'pending_withdrawals': data['withdrawal_pending_sum'],
        'total_share_distribution_transactions': share_distribution_agg['count'] or 0,
        'total_share_distribution_amount': str(share_distribution_agg['total_amount'] or Decimal('0')),
        'kyc_status': data.get('kyc_status', 'pending'),
    }
    # Single query for SHARE_DISTRIBUTION transactions (reused for recent + full list)
    share_dist_qs = list(
        Transaction.objects.filter(category=TransactionCategory.SHARE_DISTRIBUTION)
        .select_related('restaurant')
        .order_by('-created_at')[:50]
    )
    data['recent_distributions'] = [
        {'id': t.id, 'date': t.created_at.isoformat() if t.created_at else None, 'total_amount': str(t.amount), 'category': t.category or ''}
        for t in share_dist_qs[:20]
    ]
    data['share_distribution_transactions'] = [
        {
            'id': t.id,
            'amount': str(t.amount),
            'transaction_type': getattr(t, 'transaction_type', ''),
            'category': t.category or '',
            'created_at': t.created_at.isoformat() if t.created_at else None,
        }
        for t in share_dist_qs
    ]
    # Withdrawal-based transaction history (for this user)
    data['transaction_history'] = [
        {'id': w.id, 'category': 'share_withdrawal', 'amount': str(-w.amount), 'transaction_type': 'out', 'status': w.status, 'created_at': w.created_at.isoformat() if w.created_at else None}
        for w in withdrawals_list[:100]
    ]
    # Balance flow timeline (sorted by created_at in Python to avoid extra query)
    from datetime import datetime
    sorted_by_created = sorted(withdrawals_list, key=lambda w: w.created_at or datetime.min)
    data['balance_flow_timeline'] = [
        {'date': w.created_at.isoformat() if w.created_at else None, 'amount': float(-w.amount), 'type': 'withdrawal', 'status': w.status}
        for w in sorted_by_created[:100]
    ]
    data['share_growth'] = [{'date': data.get('created_at'), 'share_percentage': float(data.get('share_percentage', 0) or 0)}]
    return JsonResponse(data)


@auth_required
@require_http_methods(['GET'])
def super_admin_shareholder_list(request):
    qs = User.objects.filter(is_shareholder=True).order_by('-created_at')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    # Stats (global, not filtered by search/date for summary)
    total_shareholders = User.objects.filter(is_shareholder=True).count()
    total_share_pct = User.objects.filter(is_shareholder=True).aggregate(
        s=Sum('share_percentage')
    )['s'] or Decimal('0')
    total_balance = User.objects.filter(is_shareholder=True).aggregate(s=Sum('balance'))['s'] or Decimal('0')
    total_due_balance = User.objects.filter(is_shareholder=True).aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    pending_wd = ShareholderWithdrawal.objects.filter(status=WithdrawalStatus.PENDING).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    approved_wd = ShareholderWithdrawal.objects.filter(status=WithdrawalStatus.APPROVED).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    share_distributed = Transaction.objects.filter(category=TransactionCategory.SHARE_DISTRIBUTION).aggregate(
        s=Sum('amount')
    )['s'] or Decimal('0')
    system_balance = '0'
    try:
        ss = SuperSetting.objects.first()
        if ss:
            system_balance = str(ss.balance)
    except Exception:
        pass
    stats = {
        'total': total_shareholders,
        'total_shareholders': total_shareholders,
        'total_percentage': float(total_share_pct),
        'total_share_percentage': float(total_share_pct),
        'total_balance': str(total_balance),
        'total_due_balance': str(total_due_balance),
        'total_pending_withdrawals': str(pending_wd),
        'total_approved_withdrawals': str(approved_wd),
        'total_share_distributed': str(share_distributed),
        'system_balance': system_balance,
        'shareholder_balance': str(total_balance),
    }
    qs_paged, pagination = paginate_queryset(qs, request)
    results = [_shareholder_to_dict(u, request=request) for u in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_shareholder_create(request):
    body, image_file = _get_request_body(request)
    phone = (body.get('phone') or '').strip()
    country_code = normalize_country_code((body.get('country_code') or '').strip())
    name = (body.get('name') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
        }, status=400)
    username = f'{country_code}_{phone}'
    user, _ = User.objects.get_or_create(
        country_code=country_code,
        phone=phone,
        defaults={'username': username, 'name': name or username},
    )
    user.is_shareholder = True
    user.share_percentage = Decimal(str(body.get('share_percentage', 0)))
    user.name = name or user.name
    if image_file:
        user.image = image_file
    user.save()
    return JsonResponse(_shareholder_to_dict(user, request=request), status=201)


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
        new_phone = str(body['phone']).strip()
        new_cc = normalize_country_code(str(body.get('country_code') or u.country_code or '').strip())
        if new_phone:
            if not new_cc:
                return JsonResponse({'error': 'Country code is required.'}, status=400)
            if new_cc not in ALLOWED_COUNTRY_CODES:
                return JsonResponse({
                    'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
                }, status=400)
            if User.objects.filter(country_code=new_cc, phone=new_phone).exclude(pk=u.pk).exists():
                return JsonResponse({'error': 'Another user with this country code and phone already exists'}, status=400)
        u.phone = new_phone
    if 'country_code' in body:
        new_cc = normalize_country_code(str(body.get('country_code', '')).strip())
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
            }, status=400)
        u.country_code = new_cc
    if 'share_percentage' in body:
        u.share_percentage = Decimal(str(body['share_percentage']))
    if 'is_shareholder' in body:
        u.is_shareholder = str(body.get('is_shareholder')).lower() in ('true', '1', 'yes')
    u.save()
    return JsonResponse(_shareholder_to_dict(u, request=request))
