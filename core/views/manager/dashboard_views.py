"""Function-based views for manager dashboard. Scoped to manager's restaurant only."""
from django.http import JsonResponse
from django.db.models import Sum, Count, F
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from core.models import (
    Restaurant, Order, OrderItem, Staff, RawMaterial, OrderStatus, PaymentStatus,
    Purchase, Expenses, CustomerRestaurant, Vendor, Attendance, SuperSetting,
    Transaction, TransactionCategory,
)
from core.utils import get_restaurant_ids


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


def manager_dashboard(request):
    """
    Manager dashboard: scoped to manager's restaurant via get_restaurant_ids.
    Lock check (due_balance > due_threshold) is done by manager_unlocked decorator.
    Returns cards, graphs, tables; no cross-restaurant or SuperSetting data.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden', 'locked': False}, status=403)

    restaurants = Restaurant.objects.filter(id__in=rid)
    orders = Order.objects.filter(restaurant__in=restaurants)
    staffs = Staff.objects.filter(restaurant__in=restaurants)
    raw_materials = RawMaterial.objects.filter(restaurant__in=restaurants)

    today = timezone.now().date()

    # --- Cards ---
    order_qs_today = orders.filter(created_at__date=today).exclude(status=OrderStatus.REJECTED)
    today_sales = order_qs_today.aggregate(s=Sum('total'))['s'] or Decimal('0')
    today_orders = order_qs_today.count()

    today_purchase = Purchase.objects.filter(restaurant__in=restaurants).filter(
        created_at__date=today
    ).aggregate(s=Sum('total'))['s'] or Decimal('0')

    today_expenses = Expenses.objects.filter(restaurant__in=restaurants).filter(
        created_at__date=today
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    stock_value = raw_materials.aggregate(
        s=Sum(F('stock') * F('price'))
    )['s'] or Decimal('0')

    total_staff = staffs.count()

    customer_credit = CustomerRestaurant.objects.filter(
        restaurant__in=restaurants
    ).aggregate(s=Sum('to_pay'))['s'] or Decimal('0')

    vendor_credit = Vendor.objects.filter(
        restaurant__in=restaurants
    ).aggregate(s=Sum('to_pay'))['s'] or Decimal('0')

    # Existing metrics (backward compatible)
    pending_orders = orders.filter(
        status__in=[OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.RUNNING]
    ).count()
    active_orders = orders.exclude(status=OrderStatus.REJECTED).exclude(
        payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]
    ).count()
    active_staff = staffs.filter(is_suspend=False).count()

    try:
        low_stock_count = raw_materials.filter(stock__lte=F('min_stock')).count()
    except Exception:
        low_stock_count = 0

    # Orders by status (for manager deep relation)
    orders_by_status = {
        'pending': orders.filter(status=OrderStatus.PENDING).count(),
        'accepted': orders.filter(status=OrderStatus.ACCEPTED).count(),
        'running': orders.filter(status=OrderStatus.RUNNING).count(),
        'ready': orders.filter(status=OrderStatus.READY).count(),
        'served': orders.filter(status=OrderStatus.SERVED).count(),
        'rejected': orders.filter(status=OrderStatus.REJECTED).count(),
    }

    # Staff present today (attendance)
    staff_present_today = Attendance.objects.filter(
        staff__restaurant__in=restaurants,
        date=today,
        status='present',
    ).count()

    # Total due (restaurant due_balance)
    total_due = restaurants.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')

    # Transaction fee impact (read-only: per_transaction_fee from SuperSetting + today's txn fee)
    ss = SuperSetting.objects.first()
    per_transaction_fee = (ss.per_transaction_fee or Decimal('0')) if ss else Decimal('0')
    today_txn_fee = Transaction.objects.filter(
        restaurant__in=restaurants,
        category=TransactionCategory.TRANSACTION_FEE,
        created_at__date=today,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # --- Graphs: sales trend 7 and 30 days ---
    sales_trend_7 = []
    sales_trend_30 = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        day_orders = orders.filter(created_at__date=d).exclude(status=OrderStatus.REJECTED)
        total = day_orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
        sales_trend_7.append({
            'date': d.isoformat(),
            'total': _decimal_str(total),
            'orders': day_orders.count(),
        })
    for i in range(30):
        d = today - timedelta(days=29 - i)
        day_orders = orders.filter(created_at__date=d).exclude(status=OrderStatus.REJECTED)
        total = day_orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
        sales_trend_30.append({
            'date': d.isoformat(),
            'total': _decimal_str(total),
            'orders': day_orders.count(),
        })

    expense_trend = []
    purchase_trend = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        exp = Expenses.objects.filter(restaurant__in=restaurants).filter(
            created_at__date=d
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        pur = Purchase.objects.filter(restaurant__in=restaurants).filter(
            created_at__date=d
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        expense_trend.append({'date': d.isoformat(), 'total': _decimal_str(exp)})
        purchase_trend.append({'date': d.isoformat(), 'total': _decimal_str(pur)})

    # Top products (by order item total)
    top_products_qs = OrderItem.objects.filter(
        order__restaurant__in=restaurants,
        order__status__in=[OrderStatus.ACCEPTED, OrderStatus.RUNNING, OrderStatus.READY]
    ).values('product_id', 'product__name').annotate(
        total_quantity=Sum('quantity'),
        total_amount=Sum('total'),
    ).order_by('-total_amount')[:10]

    top_products = []
    for row in top_products_qs:
        top_products.append({
            'product_id': row['product_id'],
            'name': row.get('product__name') or 'N/A',
            'quantity': str(row.get('total_quantity') or 0),
            'total': _decimal_str(row.get('total_amount')),
        })

    # Top customers (by order total)
    top_customers_qs = Order.objects.filter(
        restaurant__in=restaurants
    ).exclude(status=OrderStatus.REJECTED).exclude(customer_id__isnull=True).values(
        'customer_id', 'customer__name'
    ).annotate(total_amount=Sum('total'), order_count=Count('id')).order_by('-total_amount')[:10]

    top_customers = []
    for row in top_customers_qs:
        top_customers.append({
            'customer_id': row['customer_id'],
            'name': row.get('customer__name') or 'N/A',
            'total': _decimal_str(row.get('total_amount')),
            'order_count': row.get('order_count') or 0,
        })

    # --- Tables ---
    recent_orders = []
    for o in orders.select_related('table').order_by('-created_at')[:15]:
        recent_orders.append({
            'id': o.id,
            'table_name': o.table.name if o.table else (o.table_number or '-'),
            'total': _decimal_str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        })

    recent_purchases = []
    for p in Purchase.objects.filter(restaurant__in=restaurants).order_by('-created_at')[:15]:
        recent_purchases.append({
            'id': p.id,
            'total': _decimal_str(p.total),
            'created_at': p.created_at.isoformat() if p.created_at else None,
        })

    low_stock_list = []
    try:
        for rm in raw_materials.filter(stock__lte=F('min_stock'))[:20]:
            low_stock_list.append({
                'id': rm.id,
                'name': rm.name,
                'stock': _decimal_str(rm.stock),
                'min_stock': _decimal_str(rm.min_stock) if getattr(rm, 'min_stock', None) is not None else '0',
                'unit_id': rm.unit_id,
            })
    except Exception:
        pass

    # Pending payments: unpaid orders
    pending_payments = []
    for o in orders.exclude(
        payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]
    ).exclude(status=OrderStatus.REJECTED).select_related('table').order_by('-created_at')[:15]:
        pending_payments.append({
            'id': o.id,
            'total': _decimal_str(o.total),
            'payment_status': o.payment_status,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        })

    # Active orders list (existing)
    active_orders_list = []
    for o in orders.exclude(status=OrderStatus.REJECTED).exclude(
        payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]
    ).select_related('table', 'waiter').order_by('-created_at')[:15]:
        active_orders_list.append({
            'id': o.id,
            'table_id': o.table_id,
            'table_name': o.table.name if o.table else None,
            'total': _decimal_str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'waiter_id': o.waiter_id,
            'waiter_name': o.waiter.user.name if o.waiter and o.waiter.user else None,
            'items_count': o.items.count(),
            'created_at': o.created_at.isoformat() if o.created_at else None,
        })

    # Waiter performance
    waiter_performance = []
    for s in staffs.filter(is_waiter=True).annotate(
        order_count=Count('served_orders')
    ).select_related('user')[:10]:
        waiter_performance.append({
            'id': s.id,
            'user_id': s.user_id,
            'name': s.user.name if s.user else '',
            'order_count': getattr(s, 'order_count', 0),
        })

    data = {
        'locked': False,
        # New cards
        'today_sales': _decimal_str(today_sales),
        'today_orders': today_orders,
        'today_purchase': _decimal_str(today_purchase),
        'today_expenses': _decimal_str(today_expenses),
        'stock_value': _decimal_str(stock_value),
        'total_staff': total_staff,
        'customer_credit': _decimal_str(customer_credit),
        'vendor_credit': _decimal_str(vendor_credit),
        # Manager deep relation stats
        'orders_by_status': orders_by_status,
        'staff_present_today': staff_present_today,
        'total_due': _decimal_str(total_due),
        'per_transaction_fee': _decimal_str(per_transaction_fee),
        'today_txn_fee': _decimal_str(today_txn_fee),
        # Graphs
        'sales_trend_7': sales_trend_7,
        'sales_trend_30': sales_trend_30,
        'expense_trend': expense_trend,
        'purchase_trend': purchase_trend,
        'top_products': top_products,
        'top_customers': top_customers,
        # Tables
        'recent_orders': recent_orders,
        'recent_purchases': recent_purchases,
        'low_stock_items': low_stock_list,
        'pending_payments': pending_payments,
        # Existing (backward compatible)
        'pending_orders': pending_orders,
        'low_stock_count': low_stock_count,
        'active_staff': active_staff,
        'active_orders': active_orders,
        'active_orders_list': active_orders_list,
        'waiter_performance': waiter_performance,
        'low_stock_alerts': low_stock_list,
    }

    return JsonResponse(data)
