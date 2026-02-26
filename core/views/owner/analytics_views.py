"""Owner analytics: revenue, orders, weekly sales, today trend, category breakdown, transaction fee, WhatsApp, QR Stand, top customers."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

from core.models import Order, OrderItem, Category, Transaction, TransactionCategory, QrStandOrder, Customer
from core.utils import get_restaurant_ids, auth_required


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


@auth_required
@require_http_methods(['GET'])
def owner_analytics(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({
            'stats': {}, 'weekly_sales': [], 'today_trend': [], 'category_breakdown': [],
            'transaction_fee_total': '0', 'whatsapp_usage_total': '0', 'qr_stand_revenue': '0',
            'top_customers': [], 'revenue_breakdown': [],
        })
    order_qs = Order.objects.filter(restaurant_id__in=rid).exclude(status='rejected')
    total_revenue = order_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    total_orders = order_qs.count()
    avg_orders = total_orders / 7 if total_orders else 0
    from core.models import CustomerRestaurant
    customer_count = CustomerRestaurant.objects.filter(restaurant_id__in=rid).values_list('customer_id', flat=True).distinct().count()
    stats = {
        'revenue': str(total_revenue),
        'orders': total_orders,
        'avg_orders': round(avg_orders, 2),
        'customers': customer_count,
    }
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    weekly_sales = []
    for i in range(7):
        d = week_ago + timedelta(days=i)
        day_total = order_qs.filter(created_at__date=d).aggregate(s=Sum('total'))['s'] or Decimal('0')
        day_name = weekdays[d.weekday()]
        weekly_sales.append({'date': d.isoformat(), 'day': day_name, 'name': day_name, 'total': str(day_total), 'sales': str(day_total), 'orders': order_qs.filter(created_at__date=d).count()})
    today_orders = order_qs.filter(created_at__date=today).order_by('created_at')
    today_trend = []
    for o in today_orders[:20]:
        today_trend.append({'time': o.created_at.isoformat() if o.created_at else None, 'total': str(o.total)})
    per_cat = OrderItem.objects.filter(order__restaurant_id__in=rid).values('product__category_id').annotate(
        total_quantity=Sum('quantity'),
        total_amount=Sum('total'),
    )
    cat_ids = [row['product__category_id'] for row in per_cat if row['product__category_id']]
    names_by_id = {}
    if cat_ids:
        for c in Category.objects.filter(id__in=cat_ids).values('id', 'name'):
            names_by_id[c['id']] = c['name'] or f"Category {c['id']}"
    total_cat_amount = float(sum((row['total_amount'] or 0) for row in per_cat))
    category_breakdown = []
    for row in per_cat:
        cid = row['product__category_id']
        amt = float(row['total_amount'] or 0)
        pct = round((amt / total_cat_amount * 100), 1) if total_cat_amount else 0
        category_breakdown.append({
            'category_id': cid,
            'name': names_by_id.get(cid) if cid else 'Uncategorized',
            'total_quantity': row['total_quantity'] or 0,
            'total_amount': str(row['total_amount'] or 0),
            'value': pct,
        })
    revenue_breakdown = category_breakdown

    tx_fee = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    whatsapp = Transaction.objects.filter(restaurant_id__in=rid, category=TransactionCategory.WHATSAPP_USAGE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    qr_stand_total = QrStandOrder.objects.filter(restaurant_id__in=rid).aggregate(s=Sum('total'))['s'] or Decimal('0')

    top_customers_qs = (
        Order.objects.filter(restaurant_id__in=rid)
        .exclude(status='rejected')
        .values('customer_id')
        .annotate(total_spent=Sum('total'), order_count=Count('id'))
        .order_by('-total_spent')[:10]
    )
    customer_ids = [x['customer_id'] for x in top_customers_qs if x['customer_id']]
    customer_names = {}
    if customer_ids:
        for c in Customer.objects.filter(id__in=customer_ids).values('id', 'name'):
            customer_names[c['id']] = c['name'] or f"Customer {c['id']}"
    top_customers = [
        {
            'customer_id': row['customer_id'],
            'name': customer_names.get(row['customer_id'], '—'),
            'total_spent': _decimal_str(row['total_spent']),
            'order_count': row['order_count'],
        }
        for row in top_customers_qs
    ]

    return JsonResponse({
        'stats': stats,
        'weekly_sales': weekly_sales,
        'today_trend': today_trend,
        'category_breakdown': category_breakdown,
        'revenue_breakdown': revenue_breakdown,
        'transaction_fee_total': _decimal_str(tx_fee),
        'whatsapp_usage_total': _decimal_str(whatsapp),
        'qr_stand_revenue': _decimal_str(qr_stand_total),
        'top_customers': top_customers,
    })
