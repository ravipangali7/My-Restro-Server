"""Function-based views for super admin dashboard."""
from datetime import timedelta
from django.http import JsonResponse
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from decimal import Decimal

from core.models import (
    User, Restaurant, SuperSetting, QrStandOrder,
    ShareholderWithdrawal, Transaction, KycStatus, WithdrawalStatus,
    QrStandOrderStatus, TransactionCategory, Order, OrderStatus,
    Purchase, Expenses, PaidRecord, ReceivedRecord, Staff, RawMaterial,
    CustomerRestaurant, Vendor,
)


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


def _date_range_for_filter(time_filter):
    """Return (start, end) for filtering. end=None means now."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if time_filter == 'today':
        return today_start, now
    if time_filter == 'yesterday':
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        return yesterday_start, yesterday_end
    if time_filter == 'weekly':
        return today_start - timedelta(days=6), now
    if time_filter == 'monthly':
        return today_start.replace(day=1), now
    if time_filter == 'yearly':
        return today_start.replace(month=1, day=1), now
    return None, None


def super_admin_dashboard(request):
    """Super admin dashboard: time filter, stats (system balance, restaurants, KYC, shareholders, withdrawals, revenue), lists, alerts."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    time_filter = request.GET.get('time', 'today')

    # SuperSetting (single row) for system balance
    setting = SuperSetting.objects.first()
    system_balance = setting.balance if setting else Decimal('0')

    # Restaurants: total, active (is_open), inactive, pending KYC, expired, due blocked
    restaurants = Restaurant.objects.select_related('user').all()
    total_restaurants = restaurants.count()
    active_restaurants = restaurants.filter(is_open=True).count()
    inactive_restaurants = total_restaurants - active_restaurants
    pending_kyc = User.objects.filter(is_owner=True, kyc_status=KycStatus.PENDING).count()
    today = timezone.now().date()
    expired_restaurants = restaurants.filter(subscription_end__lt=today).count()
    threshold = (setting.due_threshold or Decimal('0')) if setting else Decimal('0')
    due_blocked = restaurants.filter(due_balance__gt=threshold).count()

    # Shareholders
    shareholders = User.objects.filter(is_shareholder=True)
    total_shareholders = shareholders.count()
    shareholder_balance = shareholders.aggregate(s=Sum('balance'))['s'] or Decimal('0')
    distributed_balance = _decimal_str(shareholder_balance)  # or separate computed field

    # Withdrawals
    withdrawals = ShareholderWithdrawal.objects.all()
    total_withdrawals = withdrawals.count()
    pending_withdrawals = withdrawals.filter(status=WithdrawalStatus.PENDING).count()
    total_withdrawal_amount = withdrawals.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    pending_withdrawal_amount = withdrawals.filter(status=WithdrawalStatus.PENDING).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Due amount (sum of restaurant due_balance)
    total_due_amount = restaurants.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')

    date_start, date_end = _date_range_for_filter(time_filter)

    # Sales (all restaurants, time-filtered): Order total excluding REJECTED
    orders_qs = Order.objects.exclude(status=OrderStatus.REJECTED)
    if date_start is not None:
        orders_qs = orders_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            orders_qs = orders_qs.filter(created_at__lte=date_end)
    total_sales = orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    # Purchase (all restaurants, time-filtered)
    purchases_qs = Purchase.objects.all()
    if date_start is not None:
        purchases_qs = purchases_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            purchases_qs = purchases_qs.filter(created_at__lte=date_end)
    total_purchase = purchases_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    # Expenses (all restaurants, time-filtered)
    expenses_qs = Expenses.objects.all()
    if date_start is not None:
        expenses_qs = expenses_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            expenses_qs = expenses_qs.filter(created_at__lte=date_end)
    total_expenses = expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Paid records (time-filtered)
    paid_qs = PaidRecord.objects.all()
    if date_start is not None:
        paid_qs = paid_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            paid_qs = paid_qs.filter(created_at__lte=date_end)
    total_paid = paid_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Received records (time-filtered)
    received_qs = ReceivedRecord.objects.all()
    if date_start is not None:
        received_qs = received_qs.filter(created_at__gte=date_start)
        if date_end is not None:
            received_qs = received_qs.filter(created_at__lte=date_end)
    total_received = received_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # Staff & salary: count and total to_pay
    staff_count = Staff.objects.count()
    staff_to_pay = Staff.objects.aggregate(s=Sum('to_pay'))['s'] or Decimal('0')

    # Stock/Inventory: total value (stock * price) and low-stock count
    stock_value = RawMaterial.objects.aggregate(
        s=Sum(F('stock') * F('price'))
    )['s'] or Decimal('0')
    try:
        low_stock_count = RawMaterial.objects.exclude(
            min_stock__isnull=True
        ).filter(stock__lte=F('min_stock')).count()
    except Exception:
        low_stock_count = 0

    # Customer credit (to_pay / to_receive) across all CustomerRestaurant
    customer_to_pay = CustomerRestaurant.objects.aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
    customer_to_receive = CustomerRestaurant.objects.aggregate(s=Sum('to_receive'))['s'] or Decimal('0')

    # Vendor credit
    vendor_to_pay = Vendor.objects.aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
    vendor_to_receive = Vendor.objects.aggregate(s=Sum('to_receive'))['s'] or Decimal('0')

    # System revenue / earnings from transactions (filtered by time)
    transactions = Transaction.objects.filter(is_system=True)
    if date_start is not None:
        transactions = transactions.filter(created_at__gte=date_start)
        if date_end is not None:
            transactions = transactions.filter(created_at__lte=date_end)
    system_revenue = transactions.filter(transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    qr_stand_earning = transactions.filter(category=TransactionCategory.QR_STAND_ORDER).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    subscription_earning = transactions.filter(category=TransactionCategory.SUBSCRIPTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    transaction_earning = transactions.filter(category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    whatsapp_earning = transactions.filter(category=TransactionCategory.WHATSAPP_USAGE).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # QR stand order counts by status
    qr_stand_pending_count = QrStandOrder.objects.filter(status=QrStandOrderStatus.PENDING).count()
    qr_stand_total_count = QrStandOrder.objects.count()

    # Restaurant list (image, name, location, phone with country_code, status)
    restaurant_list = []
    for r in restaurants[:20]:
        restaurant_list.append({
            'id': r.id,
            'name': r.name,
            'slug': r.slug,
            'logo': r.logo.url if r.logo else None,
            'address': r.address or '',
            'is_open': r.is_open,
            'phone': r.phone or '',
            'country_code': getattr(r, 'country_code', '') or '',
        })

    # Pending: QR stand orders, KYC pending, withdrawals (with preview for dashboard)
    qr_pending_qs = QrStandOrder.objects.filter(status=QrStandOrderStatus.PENDING).select_related('restaurant')[:5]
    qr_pending = QrStandOrder.objects.filter(status=QrStandOrderStatus.PENDING).count()
    qr_stand_pending_preview = [{'id': q.id, 'restaurant_name': q.restaurant.name if q.restaurant else ''} for q in qr_pending_qs]
    kyc_pending_users = list(User.objects.filter(is_owner=True, kyc_status=KycStatus.PENDING).values('id', 'name', 'username')[:10])
    kyc_pending_list = [u['id'] for u in kyc_pending_users]
    kyc_pending_preview = [{'id': u['id'], 'name': u['name'] or u['username'] or f"#{u['id']}"} for u in kyc_pending_users]
    withdrawals_pending_list = []
    for w in ShareholderWithdrawal.objects.filter(status=WithdrawalStatus.PENDING).select_related('user')[:10]:
        withdrawals_pending_list.append({
            'id': w.id,
            'user_id': w.user_id,
            'user_name': getattr(w.user, 'name', '') or getattr(w.user, 'username', ''),
            'amount': _decimal_str(w.amount),
            'created_at': w.created_at.isoformat() if w.created_at else None,
        })

    # Platform revenue line chart: daily system revenue (transaction_type=in) for the period
    platform_revenue_line = []
    if date_start is not None:
        daily_qs = Transaction.objects.filter(
            is_system=True, transaction_type='in', created_at__gte=date_start
        )
        if date_end is not None:
            daily_qs = daily_qs.filter(created_at__lte=date_end)
        daily = (
            daily_qs.annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(value=Sum('amount'))
            .order_by('day')
        )
        for row in daily:
            platform_revenue_line.append({
                'name': row['day'].isoformat() if row['day'] else '',
                'value': float(row['value'] or 0),
                'sales': float(row['value'] or 0),
            })

    # Revenue pie: breakdown by category (from current time-filtered aggregates)
    revenue_pie = []
    if float(qr_stand_earning or 0) > 0:
        revenue_pie.append({'name': 'QR Stand', 'value': float(qr_stand_earning)})
    if float(subscription_earning or 0) > 0:
        revenue_pie.append({'name': 'Subscription', 'value': float(subscription_earning)})
    if float(transaction_earning or 0) > 0:
        revenue_pie.append({'name': 'Transaction Fee', 'value': float(transaction_earning)})
    if float(whatsapp_earning or 0) > 0:
        revenue_pie.append({'name': 'WhatsApp', 'value': float(whatsapp_earning)})

    # System alerts (counts for badges)
    alerts = {
        'new_kyc': pending_kyc,
        'pending_withdrawals': pending_withdrawals,
        'qr_stand_pending': qr_pending,
    }

    # Per-restaurant analytics (time-filtered where relevant)
    # 1) Restaurant revenue chart: daily revenue per restaurant for the period
    restaurant_revenue_chart = []
    if date_start is not None:
        orders_by_restaurant_day = Order.objects.exclude(status=OrderStatus.REJECTED).filter(created_at__gte=date_start)
        if date_end is not None:
            orders_by_restaurant_day = orders_by_restaurant_day.filter(created_at__lte=date_end)
        daily_per_restaurant = (
            orders_by_restaurant_day.annotate(day=TruncDate('created_at'))
            .values('day', 'restaurant_id', 'restaurant__name')
            .annotate(value=Sum('total'))
            .order_by('day', 'restaurant_id')
        )
        for row in daily_per_restaurant:
            restaurant_revenue_chart.append({
                'name': row['day'].isoformat() if row.get('day') else '',
                'restaurant_id': row.get('restaurant_id'),
                'restaurant_name': row.get('restaurant__name') or '',
                'value': float(row.get('value') or 0),
                'sales': float(row.get('value') or 0),
            })

    # 2) Restaurant performance comparison: revenue, order_count, due_balance per restaurant (time-filtered revenue)
    restaurant_performance = []
    for r in restaurants[:50]:
        rev_qs = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED)
        if date_start is not None:
            rev_qs = rev_qs.filter(created_at__gte=date_start)
            if date_end is not None:
                rev_qs = rev_qs.filter(created_at__lte=date_end)
        rev = rev_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = rev_qs.count()
        restaurant_performance.append({
            'restaurant_id': r.id,
            'restaurant_name': r.name,
            'revenue': str(rev),
            'order_count': order_count,
            'due_balance': str(r.due_balance),
        })

    # 3) Due balance financial summary
    by_restaurant = [
        {'restaurant_id': r.id, 'name': r.name, 'due_balance': str(r.due_balance)}
        for r in restaurants[:50]
    ]
    due_balance_financial_summary = {
        'total_due': _decimal_str(total_due_amount),
        'by_restaurant': by_restaurant,
    }

    # Global analytics (all-time / current snapshot; reuse existing aggregates, no duplicate calc)
    total_owners = User.objects.filter(is_owner=True).count()
    system_tx_all = Transaction.objects.filter(is_system=True, transaction_type='in')
    total_tx_fees = system_tx_all.filter(category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_sub_revenue = system_tx_all.filter(category=TransactionCategory.SUBSCRIPTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_qr_revenue = system_tx_all.filter(category=TransactionCategory.QR_STAND_ORDER).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_sales_all = Order.objects.exclude(status=OrderStatus.REJECTED).aggregate(s=Sum('total'))['s'] or Decimal('0')
    global_analytics = {
        'total_restaurants': total_restaurants,
        'total_owners': total_owners,
        'total_shareholders': total_shareholders,
        'total_sales': _decimal_str(total_sales_all),
        'total_transaction_fees': _decimal_str(total_tx_fees),
        'total_subscription_revenue': _decimal_str(total_sub_revenue),
        'total_qr_revenue': _decimal_str(total_qr_revenue),
        'total_system_balance': _decimal_str(system_balance),
        'total_due_balance': _decimal_str(total_due_amount),
    }

    data = {
        'time_filter': time_filter,
        'system_balance': _decimal_str(system_balance),
        'total_restaurants': total_restaurants,
        'active_restaurants': active_restaurants,
        'inactive_restaurants': inactive_restaurants,
        'pending_kyc': pending_kyc,
        'expired_restaurants': expired_restaurants,
        'due_blocked': due_blocked,
        'total_shareholders': total_shareholders,
        'shareholder_balance': _decimal_str(shareholder_balance),
        'distributed_balance': distributed_balance,
        'total_withdrawals': total_withdrawals,
        'pending_withdrawals': pending_withdrawals,
        'total_withdrawal_amount': _decimal_str(total_withdrawal_amount),
        'pending_withdrawal_amount': _decimal_str(pending_withdrawal_amount),
        'total_due_amount': _decimal_str(total_due_amount),
        'system_revenue': _decimal_str(system_revenue),
        'qr_stand_earning': _decimal_str(qr_stand_earning),
        'subscription_earning': _decimal_str(subscription_earning),
        'transaction_earning': _decimal_str(transaction_earning),
        'whatsapp_earning': _decimal_str(whatsapp_earning),
        'restaurants': restaurant_list,
        'pending_qr_stand_count': qr_pending,
        'kyc_pending_ids': kyc_pending_list,
        'kyc_pending_preview': kyc_pending_preview,
        'qr_stand_pending_preview': qr_stand_pending_preview,
        'withdrawals_pending': withdrawals_pending_list,
        'alerts': alerts,
        'revenue_pie': revenue_pie,
        'platform_revenue_line': platform_revenue_line,
        # Combined analytics (all restaurants, time-filtered where relevant)
        'total_sales': _decimal_str(total_sales),
        'total_purchase': _decimal_str(total_purchase),
        'total_expenses': _decimal_str(total_expenses),
        'total_paid': _decimal_str(total_paid),
        'total_received': _decimal_str(total_received),
        'staff_count': staff_count,
        'staff_to_pay': _decimal_str(staff_to_pay),
        'stock_value': _decimal_str(stock_value),
        'low_stock_count': low_stock_count,
        'customer_to_pay': _decimal_str(customer_to_pay),
        'customer_to_receive': _decimal_str(customer_to_receive),
        'vendor_to_pay': _decimal_str(vendor_to_pay),
        'vendor_to_receive': _decimal_str(vendor_to_receive),
        'qr_stand_total_count': qr_stand_total_count,
        # Per-restaurant analytics
        'restaurant_revenue_chart': restaurant_revenue_chart,
        'restaurant_performance': restaurant_performance,
        'due_balance_financial_summary': due_balance_financial_summary,
        'global_analytics': global_analytics,
    }

    return JsonResponse(data)
