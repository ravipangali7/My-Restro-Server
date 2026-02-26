"""Super Admin finance dashboard: order revenue, transaction amount, pending due, recent transactions. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from core.models import Order, Transaction, Restaurant


@require_http_methods(['GET'])
def super_admin_finance(request):
    order_revenue_paid = Order.objects.exclude(status='rejected').filter(
        payment_status='paid'
    ).aggregate(s=Sum('total'))['s'] or Decimal('0')
    order_revenue_pending = Order.objects.exclude(status='rejected').filter(
        payment_status='pending'
    ).aggregate(s=Sum('total'))['s'] or Decimal('0')
    transaction_amount = Transaction.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pending_due = Restaurant.objects.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    stats = {
        'order_revenue_paid': str(order_revenue_paid),
        'order_revenue_pending': str(order_revenue_pending),
        'transaction_amount': str(transaction_amount),
        'pending_due': str(pending_due),
    }
    recent = Transaction.objects.select_related('restaurant').order_by('-created_at')[:20]
    results = [
        {
            'id': t.id,
            'restaurant_id': t.restaurant_id,
            'restaurant_name': t.restaurant.name if t.restaurant else None,
            'amount': str(t.amount),
            'transaction_type': t.transaction_type,
            'payment_status': t.payment_status or '',
            'created_at': t.created_at.isoformat() if t.created_at else None,
        }
        for t in recent
    ]
    return JsonResponse({'stats': stats, 'recent_transactions': results})
