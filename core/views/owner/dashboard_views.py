"""Function-based views for owner dashboard. All data scoped to owner's restaurants."""
from datetime import timedelta, datetime as dt
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from decimal import Decimal

from core.models import (
    Restaurant,
    Order,
    Product,
    OrderStatus,
    PaymentStatus,
    QrStandOrder,
    Purchase,
    Expenses,
    PaidRecord,
    ReceivedRecord,
    Staff,
    RawMaterial,
    Transaction,
    TransactionCategory,
    CustomerRestaurant,
    Vendor,
    SuperSetting,
)
from core.utils import get_restaurant_ids
from core.services import get_super_setting


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


def _date_range_for_filter(time_filter):
    """Return (start, end) for order filtering. end=None means now."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if time_filter == 'today':
        return today_start, now
    if time_filter == 'yesterday':
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        return yesterday_start, yesterday_end
    if time_filter == 'weekly':
        week_start = today_start - timedelta(days=6)
        return week_start, now
    if time_filter == 'monthly':
        month_start = today_start.replace(day=1)
        return month_start, now
    if time_filter == 'yearly':
        year_start = today_start.replace(month=1, day=1)
        return year_start, now
    # all_time
    return None, None


def _restaurant_summary(r, date_start, date_end):
    """Build per-restaurant metrics dict. All from DB."""
    rid = r.id
    orders_qs = Order.objects.filter(restaurant_id=rid).exclude(status='rejected')
    if date_start is not None:
        orders_qs = orders_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            orders_qs = orders_qs.filter(created_at__lte=date_end)

    sales = orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    purchases = Purchase.objects.filter(restaurant_id=rid)
    if date_start is not None:
        purchases = purchases.filter(created_at__gte=date_start)
        if date_end is not None:
            purchases = purchases.filter(created_at__lte=date_end)
    purchases_total = purchases.aggregate(s=Sum('total'))['s'] or Decimal('0')

    expenses_qs = Expenses.objects.filter(restaurant_id=rid)
    if date_start is not None:
        expenses_qs = expenses_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            expenses_qs = expenses_qs.filter(created_at__lte=date_end)
    expenses_total = expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    paid_sum = PaidRecord.objects.filter(restaurant_id=rid)
    if date_start is not None:
        paid_sum = paid_sum.filter(created_at__gte=date_start)
        if date_end is not None:
            paid_sum = paid_sum.filter(created_at__lte=date_end)
    paid_total = paid_sum.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    received_qs = ReceivedRecord.objects.filter(restaurant_id=rid)
    if date_start is not None:
        received_qs = received_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            received_qs = received_qs.filter(created_at__lte=date_end)
    received_total = received_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    staff_count = Staff.objects.filter(restaurant_id=rid).count()
    staff_salary = Staff.objects.filter(restaurant_id=rid).aggregate(
        s=Sum('salary')
    )['s'] or Decimal('0')
    staff_to_pay = Staff.objects.filter(restaurant_id=rid).aggregate(
        s=Sum('to_pay')
    )['s'] or Decimal('0')

    raw_count = RawMaterial.objects.filter(restaurant_id=rid).count()
    low_stock = RawMaterial.objects.filter(
        restaurant_id=rid,
        min_stock__isnull=False,
        min_stock__gt=0,
    ).filter(stock__lt=F('min_stock')).count()

    cr_agg = CustomerRestaurant.objects.filter(restaurant_id=rid).aggregate(
        to_pay=Sum('to_pay'),
        to_receive=Sum('to_receive'),
    )
    customer_to_pay = cr_agg['to_pay'] or Decimal('0')
    customer_to_receive = cr_agg['to_receive'] or Decimal('0')

    vendor_agg = Vendor.objects.filter(restaurant_id=rid).aggregate(
        to_pay=Sum('to_pay'),
        to_receive=Sum('to_receive'),
    )
    vendor_to_pay = vendor_agg['to_pay'] or Decimal('0')
    vendor_to_receive = vendor_agg['to_receive'] or Decimal('0')

    tx_qs = Transaction.objects.filter(restaurant_id=rid).filter(
        Q(is_system=False) | Q(is_system__isnull=True)
    )
    if date_start is not None:
        tx_qs = tx_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            tx_qs = tx_qs.filter(created_at__lte=date_end)
    transactions_in = tx_qs.filter(transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    transactions_out = tx_qs.filter(transaction_type='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    qr_orders = QrStandOrder.objects.filter(restaurant_id=rid)
    if date_start is not None:
        qr_orders = qr_orders.filter(created_at__gte=date_start)
        if date_end is not None:
            qr_orders = qr_orders.filter(created_at__lte=date_end)
    qr_count = qr_orders.count()
    qr_total = qr_orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
    qr_pending = QrStandOrder.objects.filter(restaurant_id=rid, payment_status='pending').count()

    today = timezone.now().date()
    sub_active = (
        r.subscription_end is not None
        and r.subscription_end >= today
    ) if r else False

    return {
        'restaurant_id': rid,
        'restaurant_name': r.name,
        'restaurant_slug': r.slug,
        'sales': _decimal_str(sales),
        'purchases': _decimal_str(purchases_total),
        'expenses': _decimal_str(expenses_total),
        'paid_records': _decimal_str(paid_total),
        'received_records': _decimal_str(received_total),
        'staff_count': staff_count,
        'staff_salary_total': _decimal_str(staff_salary),
        'staff_to_pay': _decimal_str(staff_to_pay),
        'raw_materials_count': raw_count,
        'low_stock_count': low_stock,
        'customer_to_pay': _decimal_str(customer_to_pay),
        'customer_to_receive': _decimal_str(customer_to_receive),
        'vendor_to_pay': _decimal_str(vendor_to_pay),
        'vendor_to_receive': _decimal_str(vendor_to_receive),
        'transactions_in': _decimal_str(transactions_in),
        'transactions_out': _decimal_str(transactions_out),
        'subscription_start': str(r.subscription_start) if r.subscription_start else None,
        'subscription_end': str(r.subscription_end) if r.subscription_end else None,
        'subscription_active': sub_active,
        'qr_stand_orders_count': qr_count,
        'qr_stand_orders_total': _decimal_str(qr_total),
        'qr_stand_pending_count': qr_pending,
        'due_balance': _decimal_str(r.due_balance),
        'balance': _decimal_str(r.balance),
    }


def owner_dashboard(request):
    """
    Owner dashboard: combined and per-restaurant analytics.
    All data scoped to owner's restaurants via get_restaurant_ids(request).
    No static values; all from DB. Optional time filter for sales/orders/transactions.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    restaurant_ids = get_restaurant_ids(request)
    if not restaurant_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({
            'time_filter': 'today',
            'combined': {},
            'per_restaurant': [],
            'restaurants': [],
            'super_setting_display': {},
            'recent_orders': [],
            'hourly_sales': [],
            'sales_by_category': [],
            'sales_vs_expenses': [],
            'restaurant_comparison': [],
            'profit_trend': [],
            'top_customers': [],
            'vendor_credit_debit_summary': [],
        })

    time_filter = request.GET.get('time', 'today')
    date_start, date_end = _date_range_for_filter(time_filter)

    restaurants = Restaurant.objects.filter(id__in=restaurant_ids).order_by('name')
    orders_qs = Order.objects.filter(restaurant_id__in=restaurant_ids).exclude(status='rejected')
    if date_start is not None:
        orders_qs = orders_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            orders_qs = orders_qs.filter(created_at__lte=date_end)

    # Combined metrics
    today_revenue = orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    total_sales = today_revenue
    due_balance = Restaurant.objects.filter(id__in=restaurant_ids).aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    pending_orders = orders_qs.filter(status=OrderStatus.PENDING).count()
    active_orders = orders_qs.exclude(status__in=[OrderStatus.REJECTED]).exclude(
        payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]
    ).count()
    total_products = Product.objects.filter(restaurant_id__in=restaurant_ids).count()

    purchases_qs = Purchase.objects.filter(restaurant_id__in=restaurant_ids)
    if date_start is not None:
        purchases_qs = purchases_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            purchases_qs = purchases_qs.filter(created_at__lte=date_end)
    purchases_total = purchases_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    expenses_qs = Expenses.objects.filter(restaurant_id__in=restaurant_ids)
    if date_start is not None:
        expenses_qs = expenses_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            expenses_qs = expenses_qs.filter(created_at__lte=date_end)
    expenses_total = expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    paid_qs = PaidRecord.objects.filter(restaurant_id__in=restaurant_ids)
    if date_start is not None:
        paid_qs = paid_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            paid_qs = paid_qs.filter(created_at__lte=date_end)
    paid_total = paid_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    received_qs = ReceivedRecord.objects.filter(restaurant_id__in=restaurant_ids)
    if date_start is not None:
        received_qs = received_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            received_qs = received_qs.filter(created_at__lte=date_end)
    received_total = received_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    staff_count = Staff.objects.filter(restaurant_id__in=restaurant_ids).count()
    staff_salary = Staff.objects.filter(restaurant_id__in=restaurant_ids).aggregate(s=Sum('salary'))['s'] or Decimal('0')
    staff_to_pay = Staff.objects.filter(restaurant_id__in=restaurant_ids).aggregate(s=Sum('to_pay'))['s'] or Decimal('0')

    raw_count = RawMaterial.objects.filter(restaurant_id__in=restaurant_ids).count()
    low_stock_count = RawMaterial.objects.filter(
        restaurant_id__in=restaurant_ids,
        min_stock__isnull=False,
        min_stock__gt=0,
    ).filter(stock__lt=F('min_stock')).count()

    cr_agg = CustomerRestaurant.objects.filter(restaurant_id__in=restaurant_ids).aggregate(
        to_pay=Sum('to_pay'),
        to_receive=Sum('to_receive'),
    )
    customer_to_pay = cr_agg['to_pay'] or Decimal('0')
    customer_to_receive = cr_agg['to_receive'] or Decimal('0')

    vendor_agg = Vendor.objects.filter(restaurant_id__in=restaurant_ids).aggregate(
        to_pay=Sum('to_pay'),
        to_receive=Sum('to_receive'),
    )
    vendor_to_pay = vendor_agg['to_pay'] or Decimal('0')
    vendor_to_receive = vendor_agg['to_receive'] or Decimal('0')

    tx_qs = Transaction.objects.filter(restaurant_id__in=restaurant_ids).filter(
        Q(is_system=False) | Q(is_system__isnull=True)
    )
    if date_start is not None:
        tx_qs = tx_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            tx_qs = tx_qs.filter(created_at__lte=date_end)
    transactions_in = tx_qs.filter(transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    transactions_out = tx_qs.filter(transaction_type='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    qr_qs = QrStandOrder.objects.filter(restaurant_id__in=restaurant_ids)
    if date_start is not None:
        qr_qs = qr_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            qr_qs = qr_qs.filter(created_at__lte=date_end)
    qr_stand_count = qr_qs.count()
    qr_stand_total = qr_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    qr_stand_pending = QrStandOrder.objects.filter(
        restaurant_id__in=restaurant_ids,
        payment_status='pending'
    ).count()

    customers_today = orders_qs.values('customer').distinct().count()
    total_orders = orders_qs.count()
    restaurant_count = len(restaurant_ids)

    # Staff by role (manager vs waiter)
    staff_manager_count = Staff.objects.filter(restaurant_id__in=restaurant_ids, is_manager=True).count()
    staff_waiter_count = Staff.objects.filter(restaurant_id__in=restaurant_ids, is_waiter=True).count()

    # Order status distribution
    order_status_counts = dict(
        Order.objects.filter(restaurant_id__in=restaurant_ids)
        .values('status').annotate(c=Count('id')).values_list('status', 'c')
    )
    order_status_distribution = [
        {'status': s, 'count': order_status_counts.get(s, 0)}
        for s in [OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.RUNNING,
                  OrderStatus.READY, OrderStatus.SERVED, OrderStatus.REJECTED]
    ]

    # Transaction fee and subscription fee (from Transaction model, in period)
    tx_fee_qs = Transaction.objects.filter(
        restaurant_id__in=restaurant_ids,
        category=TransactionCategory.TRANSACTION_FEE,
    )
    sub_fee_qs = Transaction.objects.filter(
        restaurant_id__in=restaurant_ids,
        category=TransactionCategory.SUBSCRIPTION_FEE,
    )
    if date_start is not None:
        tx_fee_qs = tx_fee_qs.filter(created_at__gte=date_start)
        sub_fee_qs = sub_fee_qs.filter(created_at__gte=date_start)
    if date_end is not None:
        tx_fee_qs = tx_fee_qs.filter(created_at__lte=date_end)
        sub_fee_qs = sub_fee_qs.filter(created_at__lte=date_end)
    transaction_fee_total = tx_fee_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    subscription_fee_total = sub_fee_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Salary paid in period (PaidRecord with staff_id)
    salary_paid_qs = PaidRecord.objects.filter(
        restaurant_id__in=restaurant_ids,
        staff_id__isnull=False,
    )
    if date_start is not None:
        salary_paid_qs = salary_paid_qs.filter(created_at__gte=date_start)
    if date_end is not None:
        salary_paid_qs = salary_paid_qs.filter(created_at__lte=date_end)
    salary_paid_total = salary_paid_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Subscription status overview
    today = timezone.now().date()
    subscription_active_count = sum(
        1 for r in restaurants
        if r.subscription_end is not None and r.subscription_end >= today
    )
    subscription_expired_count = restaurant_count - subscription_active_count

    # Profit/Loss = (Sales + Received) - (Purchase + Expenses + Salary + Transaction Fee + Subscription + QR Cost)
    total_outflow = (
        purchases_total + expenses_total + salary_paid_total +
        transaction_fee_total + subscription_fee_total + qr_stand_total
    )
    profit_loss = (today_revenue + received_total) - total_outflow

    combined = {
        'today_revenue': _decimal_str(today_revenue),
        'total_sales': _decimal_str(total_sales),
        'due_balance': _decimal_str(due_balance),
        'pending_orders': pending_orders,
        'active_orders': active_orders,
        'total_orders': total_orders,
        'restaurant_count': restaurant_count,
        'total_products': total_products,
        'purchases_total': _decimal_str(purchases_total),
        'expenses_total': _decimal_str(expenses_total),
        'paid_records_total': _decimal_str(paid_total),
        'received_records_total': _decimal_str(received_total),
        'staff_count': staff_count,
        'staff_manager_count': staff_manager_count,
        'staff_waiter_count': staff_waiter_count,
        'staff_salary_total': _decimal_str(staff_salary),
        'staff_to_pay': _decimal_str(staff_to_pay),
        'raw_materials_count': raw_count,
        'low_stock_count': low_stock_count,
        'customer_to_pay': _decimal_str(customer_to_pay),
        'customer_to_receive': _decimal_str(customer_to_receive),
        'vendor_to_pay': _decimal_str(vendor_to_pay),
        'vendor_to_receive': _decimal_str(vendor_to_receive),
        'transactions_in': _decimal_str(transactions_in),
        'transactions_out': _decimal_str(transactions_out),
        'qr_stand_orders': qr_stand_count,
        'qr_stand_total': _decimal_str(qr_stand_total),
        'qr_stand_pending': qr_stand_pending,
        'customers_today': customers_today,
        'transaction_fee_total': _decimal_str(transaction_fee_total),
        'subscription_fee_total': _decimal_str(subscription_fee_total),
        'subscription_active_count': subscription_active_count,
        'subscription_expired_count': subscription_expired_count,
        'profit_loss': _decimal_str(profit_loss),
        'order_status_distribution': order_status_distribution,
    }

    per_restaurant = []
    for r in restaurants:
        per_restaurant.append(_restaurant_summary(r, date_start, date_end))

    super_setting_display = {}
    try:
        ss = get_super_setting()
        super_setting_display = {
            'due_threshold': _decimal_str(ss.due_threshold),
            'subscription_fee_per_month': _decimal_str(ss.subscription_fee_per_month),
            'per_qr_stand_price': _decimal_str(ss.per_qr_stand_price),
        }
    except Exception:
        pass

    restaurant_list = []
    for r in restaurants[:50]:
        restaurant_list.append({
            'id': r.id,
            'name': r.name,
            'slug': r.slug,
            'phone': r.phone or '',
            'address': r.address or '',
            'logo': r.logo.url if r.logo else None,
            'balance': _decimal_str(r.balance),
            'due_balance': _decimal_str(r.due_balance),
            'is_open': r.is_open,
            'subscription_start': str(r.subscription_start) if r.subscription_start else None,
            'subscription_end': str(r.subscription_end) if r.subscription_end else None,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        })

    recent_orders = []
    for o in orders_qs.select_related('table', 'customer', 'waiter').order_by('-created_at')[:10]:
        recent_orders.append({
            'id': o.id,
            'restaurant_id': o.restaurant_id,
            'total': _decimal_str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'order_type': o.order_type,
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'table_id': o.table_id,
            'table_name': o.table.name if o.table else None,
            'customer_id': o.customer_id,
            'customer_name': o.customer.name if o.customer else None,
            'waiter_id': o.waiter_id,
            'items_count': o.items.count(),
        })

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hourly_sales = []
    for h in range(24):
        h_start = today_start.replace(hour=h, minute=0, second=0, microsecond=0)
        h_end = today_start.replace(hour=h, minute=59, second=59, microsecond=999999)
        s = orders_qs.filter(
            created_at__gte=h_start,
            created_at__lte=h_end
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        hourly_sales.append({'name': f'{h}:00', 'sales': float(s)})

    from core.models import OrderItem
    from core.models import Category
    per_cat = OrderItem.objects.filter(
        order__restaurant_id__in=restaurant_ids
    ).values('product__category_id').annotate(
        total_amount=Sum('total'),
    )
    cat_ids = [x['product__category_id'] for x in per_cat if x['product__category_id']]
    names_by_id = {}
    if cat_ids:
        for c in Category.objects.filter(id__in=cat_ids).values('id', 'name'):
            names_by_id[c['id']] = c['name'] or f"Category {c['id']}"
    total_cat = sum(float(x['total_amount'] or 0) for x in per_cat)
    sales_by_category = []
    for row in per_cat:
        cid = row['product__category_id']
        amt = float(row['total_amount'] or 0)
        pct = round((amt / total_cat * 100), 1) if total_cat else 0
        sales_by_category.append({
            'category_id': cid,
            'name': names_by_id.get(cid, 'Uncategorized'),
            'value': pct,
            'total_amount': str(row['total_amount'] or 0),
        })

    # Sales vs Expenses (last 14 days)
    now = timezone.now()
    sales_vs_expenses = []
    for i in range(14):
        d = (now.date() - timedelta(days=13 - i))
        day_start = timezone.make_aware(dt.combine(d, dt.min.time()))
        day_end = day_start + timedelta(days=1)
        day_orders = Order.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).exclude(status='rejected')
        day_sales = day_orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
        day_exp = Expenses.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_purchase = Purchase.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        sales_vs_expenses.append({
            'name': d.strftime('%m/%d'),
            'date': d.isoformat(),
            'sales': float(day_sales),
            'expenses': float(day_exp + day_purchase),
        })

    # Restaurant comparison (bar) - use per_restaurant sales
    restaurant_comparison = [
        {'name': pr['restaurant_name'], 'sales': float(pr['sales']), 'restaurant_id': pr['restaurant_id']}
        for pr in per_restaurant
    ]

    # Profit trend (last 14 days)
    profit_trend = []
    for i in range(14):
        d = (now.date() - timedelta(days=13 - i))
        day_start = timezone.make_aware(dt.combine(d, dt.min.time()))
        day_end = day_start + timedelta(days=1)
        day_orders = Order.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).exclude(status='rejected')
        day_sales = day_orders.aggregate(s=Sum('total'))['s'] or Decimal('0')
        day_received = ReceivedRecord.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_exp = Expenses.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_purchase = Purchase.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        day_salary = PaidRecord.objects.filter(
            restaurant_id__in=restaurant_ids,
            staff_id__isnull=False,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_tx_fee = Transaction.objects.filter(
            restaurant_id__in=restaurant_ids,
            category=TransactionCategory.TRANSACTION_FEE,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_sub = Transaction.objects.filter(
            restaurant_id__in=restaurant_ids,
            category=TransactionCategory.SUBSCRIPTION_FEE,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        day_qr = QrStandOrder.objects.filter(
            restaurant_id__in=restaurant_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        day_profit = (day_sales + day_received) - (day_purchase + day_exp + day_salary + day_tx_fee + day_sub + day_qr)
        profit_trend.append({
            'name': d.strftime('%m/%d'),
            'date': d.isoformat(),
            'profit': float(day_profit),
        })

    # Top customers (by order total for owner's restaurants)
    from core.models import Customer
    top_customers_qs = (
        Order.objects.filter(restaurant_id__in=restaurant_ids)
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
            'total_spent': str(row['total_spent'] or 0),
            'order_count': row['order_count'],
        }
        for row in top_customers_qs
    ]

    # Vendor credit/debit summary (already in combined; add as chart-friendly list)
    vendor_credit_debit_summary = [
        {'name': 'To Pay', 'value': float(vendor_to_pay), 'type': 'to_pay'},
        {'name': 'To Receive', 'value': float(vendor_to_receive), 'type': 'to_receive'},
    ]

    data = {
        'time_filter': time_filter,
        'combined': combined,
        'per_restaurant': per_restaurant,
        'restaurants': restaurant_list,
        'super_setting_display': super_setting_display,
        'recent_orders': recent_orders,
        'hourly_sales': hourly_sales,
        'sales_by_category': sales_by_category,
        'sales_vs_expenses': sales_vs_expenses,
        'restaurant_comparison': restaurant_comparison,
        'profit_trend': profit_trend,
        'top_customers': top_customers,
        'vendor_credit_debit_summary': vendor_credit_debit_summary,
    }
    return JsonResponse(data)
