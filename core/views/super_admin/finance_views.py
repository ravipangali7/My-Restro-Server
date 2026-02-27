"""Super Admin finance dashboard: order revenue, income/expense, net profit, fees, recent transactions. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from core.models import (
    Order, Transaction, Restaurant,
    PaidRecord, ReceivedRecord, Expenses, Purchase,
    TransactionCategory,
)


@require_http_methods(['GET'])
def super_admin_finance(request):
    order_revenue_paid = Order.objects.exclude(status='rejected').filter(
        payment_status__in=['paid', 'success']
    ).aggregate(s=Sum('total'))['s'] or Decimal('0')
    order_revenue_pending = Order.objects.exclude(status='rejected').filter(
        payment_status='pending'
    ).aggregate(s=Sum('total'))['s'] or Decimal('0')
    transaction_amount = Transaction.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pending_due = Restaurant.objects.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')

    total_income = ReceivedRecord.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_income += Transaction.objects.filter(transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    total_expense = (Expenses.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0'))
    total_expense += PaidRecord.objects.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_expense += Purchase.objects.aggregate(s=Sum('total'))['s'] or Decimal('0')

    net_profit = total_income - total_expense

    system_tx_fee = Transaction.objects.filter(
        is_system=True, category=TransactionCategory.TRANSACTION_FEE
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    subscription_fee = Transaction.objects.filter(
        is_system=True, category=TransactionCategory.SUBSCRIPTION_FEE
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    stats = {
        'order_revenue_paid': str(order_revenue_paid),
        'order_revenue_pending': str(order_revenue_pending),
        'transaction_amount': str(transaction_amount),
        'pending_due': str(pending_due),
        'total_revenue': str(order_revenue_paid),
        'pending_dues': str(pending_due),
        'total_income': str(total_income),
        'total_expense': str(total_expense),
        'net_profit': str(net_profit),
        'system_transaction_fee': str(system_tx_fee),
        'subscription_fee_collected': str(subscription_fee),
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
    return JsonResponse({'stats': stats, 'recent_transactions': results, **stats})
