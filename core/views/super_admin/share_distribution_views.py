"""Super Admin share distribution: list system balance, distribution day, related transactions; run distribution."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model

from core.models import SuperSetting, Transaction, TransactionCategory
from core import services

User = get_user_model()


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


@require_http_methods(['GET'])
def super_admin_share_distribution_preview(request):
    """GET: system_balance and shareholders with share_percentage and computed_amount (preview only, no apply)."""
    setting = SuperSetting.objects.first()
    system_balance = Decimal(_decimal_str(setting.balance if setting else 0))
    shareholders = list(
        User.objects.filter(is_shareholder=True, share_percentage__isnull=False)
        .exclude(share_percentage=0)
        .order_by('name', 'username')
    )
    total_pct = sum((u.share_percentage or Decimal('0')) for u in shareholders)
    preview = []
    for u in shareholders:
        pct = u.share_percentage or Decimal('0')
        if pct <= 0:
            continue
        amount = (system_balance * pct / Decimal('100')).quantize(Decimal('0.01'))
        preview.append({
            'id': u.id,
            'name': getattr(u, 'name', '') or getattr(u, 'username', '') or f'User #{u.id}',
            'share_percentage': str(pct),
            'computed_amount': str(amount),
        })
    return JsonResponse({
        'system_balance': str(system_balance),
        'total_percentage': float(total_pct),
        'shareholders': preview,
    })


@require_http_methods(['GET'])
def super_admin_share_distribution_list(request):
    """GET: system_balance, share_distribution_day, transactions (share_distribution + share_withdrawal)."""
    setting = SuperSetting.objects.first()
    system_balance = _decimal_str(setting.balance if setting else 0)
    share_distribution_day = setting.share_distribution_day if setting else None

    transactions_qs = Transaction.objects.filter(
        category__in=[TransactionCategory.SHARE_DISTRIBUTION, TransactionCategory.SHARE_WITHDRAWAL]
    ).order_by('-created_at')[:50]

    transactions = [
        {
            'id': t.id,
            'amount': _decimal_str(t.amount),
            'category': t.category or '',
            'transaction_type': t.transaction_type or '',
            'remarks': t.remarks or '',
            'created_at': t.created_at.isoformat() if t.created_at else None,
        }
        for t in transactions_qs
    ]

    return JsonResponse({
        'system_balance': system_balance,
        'share_distribution_day': share_distribution_day,
        'transactions': transactions,
    })


@require_http_methods(['POST'])
def super_admin_share_distribution_run(request):
    """POST: run apply_share_distribution(). Returns { success: true }."""
    services.apply_share_distribution()
    return JsonResponse({'success': True, 'message': 'Share distribution run completed.'})
