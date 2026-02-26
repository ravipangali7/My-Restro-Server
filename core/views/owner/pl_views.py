"""Owner P&L: Profit/Loss = (Sales + Received) - (Purchase + Expenses + Salary + Transaction Fee + Subscription + QR Cost); monthly, yearly, per-restaurant."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from calendar import monthrange

from core.models import (
    Order, Expenses, PaidRecord, ReceivedRecord, Purchase,
    Transaction, TransactionCategory, QrStandOrder, Restaurant,
)
from core.utils import get_restaurant_ids, auth_required


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


@auth_required
@require_http_methods(['GET'])
def owner_pl(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({
            'stats': {}, 'expense_breakdown': [], 'monthly': [], 'yearly': [], 'per_restaurant': [],
            'payment_pie': [], 'order_type_pie': [], 'cash_flow': {},
        })
    order_qs = Order.objects.filter(restaurant_id__in=rid).exclude(status='rejected')
    revenue = order_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    received_total = ReceivedRecord.objects.filter(restaurant_id__in=rid).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    expense_qs = Expenses.objects.filter(restaurant_id__in=rid)
    expenses_total = expense_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    purchase_total = Purchase.objects.filter(restaurant_id__in=rid).aggregate(s=Sum('total'))['s'] or Decimal('0')
    salary_paid = PaidRecord.objects.filter(restaurant_id__in=rid, staff_id__isnull=False).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    tx_fee = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    sub_fee = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.SUBSCRIPTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    qr_cost = QrStandOrder.objects.filter(restaurant_id__in=rid).aggregate(s=Sum('total'))['s'] or Decimal('0')
    profit_loss = (revenue + received_total) - (purchase_total + expenses_total + salary_paid + tx_fee + sub_fee + qr_cost)
    stats = {
        'revenue': _decimal_str(revenue),
        'received': _decimal_str(received_total),
        'expenses': _decimal_str(expenses_total),
        'purchase': _decimal_str(purchase_total),
        'salary': _decimal_str(salary_paid),
        'transaction_fee': _decimal_str(tx_fee),
        'subscription': _decimal_str(sub_fee),
        'qr_cost': _decimal_str(qr_cost),
        'net_profit': _decimal_str(profit_loss),
    }
    expense_breakdown = [
        {'name': 'Purchase', 'amount': _decimal_str(purchase_total)},
        {'name': 'Expenses', 'amount': _decimal_str(expenses_total)},
        {'name': 'Staff salary', 'amount': _decimal_str(salary_paid)},
        {'name': 'Transaction fee', 'amount': _decimal_str(tx_fee)},
        {'name': 'Subscription', 'amount': _decimal_str(sub_fee)},
        {'name': 'QR cost', 'amount': _decimal_str(qr_cost)},
        {'name': 'Profit/Loss', 'amount': _decimal_str(profit_loss)},
    ]
    now = timezone.now().date()
    monthly = []
    for i in range(12):
        start = (now - timedelta(days=30 * i)).replace(day=1)
        last = monthrange(start.year, start.month)[1]
        end = start.replace(day=last)
        rev = order_qs.filter(created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        rec = ReceivedRecord.objects.filter(restaurant_id__in=rid, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        exp = expense_qs.filter(created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        pur = Purchase.objects.filter(restaurant_id__in=rid, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        sal = PaidRecord.objects.filter(restaurant_id__in=rid, staff_id__isnull=False, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        tf = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.TRANSACTION_FEE, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        sf = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.SUBSCRIPTION_FEE, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        qr = QrStandOrder.objects.filter(restaurant_id__in=rid, created_at__date__gte=start, created_at__date__lte=end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        pl = (rev + rec) - (pur + exp + sal + tf + sf + qr)
        monthly.append({
            'month': start.strftime('%Y-%m'),
            'revenue': _decimal_str(rev),
            'expenses': _decimal_str(exp),
            'profit_loss': _decimal_str(pl),
        })
    yearly = []
    for y in range(3):
        year_start = now.replace(month=1, day=1) - timedelta(days=365 * y)
        year_start = year_start.replace(month=1, day=1)
        year_end = year_start.replace(month=12, day=31)
        rev = order_qs.filter(created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        rec = ReceivedRecord.objects.filter(restaurant_id__in=rid, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        exp = Expenses.objects.filter(restaurant_id__in=rid, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        pur = Purchase.objects.filter(restaurant_id__in=rid, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        sal = PaidRecord.objects.filter(restaurant_id__in=rid, staff_id__isnull=False, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        tf = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.TRANSACTION_FEE, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        sf = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.SUBSCRIPTION_FEE, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        qr = QrStandOrder.objects.filter(restaurant_id__in=rid, created_at__date__gte=year_start, created_at__date__lte=year_end).aggregate(s=Sum('total'))['s'] or Decimal('0')
        pl = (rev + rec) - (pur + exp + sal + tf + sf + qr)
        yearly.append({
            'year': str(year_start.year),
            'revenue': _decimal_str(rev),
            'expenses': _decimal_str(exp),
            'profit_loss': _decimal_str(pl),
        })
    per_restaurant = []
    for r in Restaurant.objects.filter(id__in=rid).order_by('name'):
        rev = Order.objects.filter(restaurant=r).exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
        rec = ReceivedRecord.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        exp = Expenses.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        pur = Purchase.objects.filter(restaurant=r).aggregate(s=Sum('total'))['s'] or Decimal('0')
        sal = PaidRecord.objects.filter(restaurant=r, staff_id__isnull=False).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        tf = Transaction.objects.filter(restaurant=r, category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        sf = Transaction.objects.filter(restaurant=r, category=TransactionCategory.SUBSCRIPTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        qr = QrStandOrder.objects.filter(restaurant=r).aggregate(s=Sum('total'))['s'] or Decimal('0')
        pl = (rev + rec) - (pur + exp + sal + tf + sf + qr)
        per_restaurant.append({
            'restaurant_id': r.id,
            'restaurant_name': r.name,
            'revenue': _decimal_str(rev),
            'expenses': _decimal_str(exp),
            'profit_loss': _decimal_str(pl),
        })
    payment_pie = list(order_qs.values('payment_method').annotate(total=Sum('total')).values('payment_method', 'total'))
    for p in payment_pie:
        p['total'] = str(p['total'])
    order_type_pie = list(order_qs.values('order_type').annotate(total=Sum('total')).values('order_type', 'total'))
    for p in order_type_pie:
        p['total'] = str(p['total'])
    paid_total = PaidRecord.objects.filter(restaurant_id__in=rid).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    cash_flow = {'total_paid': _decimal_str(paid_total), 'total_received': _decimal_str(received_total)}
    return JsonResponse({
        'stats': stats,
        'expense_breakdown': expense_breakdown,
        'monthly': monthly,
        'yearly': yearly,
        'per_restaurant': per_restaurant,
        'payment_pie': payment_pie,
        'order_type_pie': order_type_pie,
        'cash_flow': cash_flow,
    })
