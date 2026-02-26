"""Super Admin withdrawals list, create, detail, update, delete, approve/reject. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum

from core.models import ShareholderWithdrawal, User, Transaction, TransactionCategory, SuperSetting
from core.utils import auth_required


def _require_super_admin(request):
    if not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Super admin required'}, status=403)
    return None


def _user_eligible_dict(u, user_type='user'):
    balance = getattr(u, 'balance', Decimal('0')) or Decimal('0')
    if isinstance(balance, (int, float)):
        balance = Decimal(str(balance))
    return {
        'id': u.id,
        'name': getattr(u, 'name', '') or getattr(u, 'username', '') or f'User #{u.id}',
        'balance': str(balance),
        'type': user_type,
    }


@auth_required
@require_http_methods(['GET'])
def super_admin_withdrawal_eligible_users(request):
    """Return users and shareholders eligible for withdrawal (for dropdown)."""
    err = _require_super_admin(request)
    if err:
        return err
    results = []
    # Shareholders (is_shareholder=True)
    shareholders = User.objects.filter(is_shareholder=True).order_by('name', 'username')
    for u in shareholders:
        results.append(_user_eligible_dict(u, 'shareholder'))
    # Owners (is_owner=True) not already in shareholders
    owner_ids = set(r['id'] for r in results)
    owners = User.objects.filter(is_owner=True).exclude(id__in=owner_ids).order_by('name', 'username')
    for u in owners:
        results.append(_user_eligible_dict(u, 'owner'))
    return JsonResponse({'results': results})


def _withdrawal_to_dict(w):
    return {
        'id': w.id,
        'user_id': w.user_id,
        'user_name': getattr(w.user, 'name', '') or getattr(w.user, 'username', ''),
        'user_image': w.user.image.url if getattr(w.user, 'image', None) and w.user.image else None,
        'amount': str(w.amount),
        'status': w.status,
        'reject_reason': w.reject_reason or '',
        'remarks': w.remarks or '',
        'created_at': w.created_at.isoformat() if w.created_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def super_admin_withdrawal_list(request):
    err = _require_super_admin(request)
    if err:
        return err
    qs = ShareholderWithdrawal.objects.all().select_related('user')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    total = qs.count()
    pending = qs.filter(status='pending').count()
    approved = qs.filter(status='approved').count()
    rejected = qs.filter(status='reject').count()
    total_amount = qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pending_amount = qs.filter(status='pending').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    stats = {
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'total_amount': str(total_amount),
        'pending_amount': str(pending_amount),
    }
    results = [_withdrawal_to_dict(w) for w in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@auth_required
@require_http_methods(['GET'])
def super_admin_withdrawal_detail(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    w = get_object_or_404(ShareholderWithdrawal, pk=pk)
    data = _withdrawal_to_dict(w)
    data['user_balance_current'] = str(getattr(w.user, 'balance', Decimal('0')) or Decimal('0'))
    related = (
        Transaction.objects.filter(
            is_system=True,
            category=TransactionCategory.SHARE_WITHDRAWAL,
            remarks__icontains=f'Share withdrawal #{w.id}',
        )
        .order_by('-created_at')
        .first()
    )
    data['related_transaction'] = None
    if related:
        data['related_transaction'] = {
            'id': related.id,
            'amount': str(related.amount),
            'category': related.category or '',
            'created_at': related.created_at.isoformat() if related.created_at else None,
            'remarks': related.remarks or '',
        }
    amount_debited = w.amount
    fee_credited = Decimal('0')
    fee_tx = (
        Transaction.objects.filter(
            is_system=True,
            category=TransactionCategory.TRANSACTION_FEE,
            remarks__icontains=f'share withdrawal #{w.id}',
        )
        .order_by('-created_at')
        .first()
    )
    if fee_tx:
        fee_credited = fee_tx.amount
    data['system_balance_impact'] = {
        'amount_debited': str(amount_debited),
        'fee_credited': str(fee_credited),
    }
    return JsonResponse(data)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_withdrawal_create(request):
    err = _require_super_admin(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    user_id = body.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    user = get_object_or_404(User, pk=user_id)
    amount = Decimal(str(body.get('amount', 0)))
    if amount <= 0:
        return JsonResponse({'error': 'amount must be positive'}, status=400)
    balance = getattr(user, 'balance', Decimal('0')) or Decimal('0')
    if isinstance(balance, (int, float)):
        balance = Decimal(str(balance))
    if balance < amount:
        return JsonResponse({'error': 'Insufficient balance'}, status=400)
    w = ShareholderWithdrawal(
        user=user,
        amount=amount,
        status=body.get('status', 'pending'),
        reject_reason=(body.get('reject_reason') or '')[:10000],
        remarks=(body.get('remarks') or '')[:10000],
    )
    w.save()
    return JsonResponse(_withdrawal_to_dict(w), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_withdrawal_update(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    w = get_object_or_404(ShareholderWithdrawal, pk=pk)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    if 'user_id' in body:
        w.user = get_object_or_404(User, pk=body['user_id'])
    if 'amount' in body:
        w.amount = Decimal(str(body['amount']))
    if 'status' in body:
        w.status = body['status']
    if 'reject_reason' in body:
        w.reject_reason = str(body.get('reject_reason', ''))[:10000]
    if 'remarks' in body:
        w.remarks = str(body.get('remarks', ''))[:10000]
    # Validate balance when amount or user changes (only for pending; approved already deducted)
    if w.status == 'pending' and ('amount' in body or 'user_id' in body):
        u = w.user
        bal = getattr(u, 'balance', Decimal('0')) or Decimal('0')
        if isinstance(bal, (int, float)):
            bal = Decimal(str(bal))
        if bal < w.amount:
            return JsonResponse({'error': 'Insufficient balance'}, status=400)
    w.save()
    return JsonResponse(_withdrawal_to_dict(w))


@csrf_exempt
@auth_required
@require_http_methods(['DELETE'])
def super_admin_withdrawal_delete(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    w = get_object_or_404(ShareholderWithdrawal, pk=pk)
    w.delete()
    return JsonResponse({'success': True})


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_withdrawal_approve_reject(request, pk):
    w = get_object_or_404(ShareholderWithdrawal, pk=pk)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    if 'status' in body:
        w.status = body['status']
    if 'reject_reason' in body:
        w.reject_reason = str(body.get('reject_reason', ''))
    if body.get('status') == 'approved':
        user = w.user
        balance = getattr(user, 'balance', Decimal('0')) or Decimal('0')
        if isinstance(balance, (int, float)):
            balance = Decimal(str(balance))
        if balance < w.amount:
            return JsonResponse({'error': 'Insufficient balance'}, status=400)
    w.save()
    return JsonResponse(_withdrawal_to_dict(w))
