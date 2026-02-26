"""Super Admin transactions list with filters and stats. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count

from core.models import Transaction


def _tx_to_dict(t):
    return {
        'id': t.id,
        'restaurant_id': t.restaurant_id,
        'restaurant_name': t.restaurant.name if t.restaurant else None,
        'amount': str(t.amount),
        'transaction_type': t.transaction_type,
        'category': t.category or '',
        'payment_status': t.payment_status or '',
        'remarks': t.remarks or '',
        'created_at': t.created_at.isoformat() if t.created_at else None,
    }


@require_http_methods(['GET'])
def super_admin_transaction_list(request):
    qs = Transaction.objects.all().select_related('restaurant')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    tx_type = request.GET.get('type')
    if tx_type == 'in':
        qs = qs.filter(transaction_type='in')
    elif tx_type == 'out':
        qs = qs.filter(transaction_type='out')
    category = request.GET.get('category')
    if category:
        qs = qs.filter(category=category)
    total_amount = qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    revenue = qs.filter(transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pending = qs.filter(payment_status='pending').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    success = qs.filter(payment_status='success').count()
    failed = qs.count() - success
    stats = {
        'total': str(total_amount),
        'revenue': str(revenue),
        'pending': str(pending),
        'success_count': success,
        'failed_count': failed,
    }
    by_cat = list(qs.values('category').annotate(total=Sum('amount')).values('category', 'total'))
    for x in by_cat:
        x['total'] = str(x['total'] or 0)
    stats['by_category'] = by_cat
    results = [_tx_to_dict(t) for t in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})
