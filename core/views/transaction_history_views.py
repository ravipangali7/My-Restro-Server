"""
Role-based Transaction History: unified stats and rows from Orders, Payments, Expenses, Purchases.
Shared helper builds data; one view per role with strict scoping.
"""
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from core.models import Order, ReceivedRecord, PaidRecord, Expenses, Purchase, Transaction, Restaurant
from core.utils import get_restaurant_ids, get_waiter_staff_id, get_customer_id_from_request
from django.db.models.functions import TruncDate


def _row(date_str, tx_type, description, amount, reference_id, restaurant_id=None, restaurant_name=None):
    """Build a unified transaction row (snake_case)."""
    r = {
        'date': date_str,
        'type': tx_type,
        'description': description,
        'amount': str(amount),
        'reference_id': reference_id,
    }
    if restaurant_id is not None:
        r['restaurant_id'] = restaurant_id
    if restaurant_name is not None:
        r['restaurant_name'] = restaurant_name
    return r


def get_transaction_history_data(
    restaurant_ids=None,
    waiter_staff_id=None,
    customer_id=None,
    date_from=None,
    date_to=None,
    page=1,
    page_size=20,
):
    """
    Build stats and paginated unified rows.
    - restaurant_ids: None = all (super_admin), [] = none, [id,...] = scope
    - waiter_staff_id: set for waiter scope (orders served by this staff)
    - customer_id: set for customer scope (their orders/payments)
    Returns: dict with stats, results (list), pagination (page, page_size, total_count).
    """
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), 500)

    # --- Waiter scope ---
    if waiter_staff_id is not None:
        order_qs = Order.objects.filter(waiter_id=waiter_staff_id).select_related('restaurant')
        if date_from:
            order_qs = order_qs.filter(created_at__date__gte=date_from)
        if date_to:
            order_qs = order_qs.filter(created_at__date__lte=date_to)
        revenue = order_qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = order_qs.count()
        rows = []
        for o in order_qs.order_by('-created_at'):
            rows.append(_row(
                o.created_at.isoformat() if o.created_at else '',
                'order',
                f"Order #{o.id}",
                o.total,
                o.id,
                o.restaurant_id,
                o.restaurant.name if o.restaurant else None,
            ))
        received_qs = ReceivedRecord.objects.filter(order__waiter_id=waiter_staff_id).select_related('order', 'restaurant')
        if date_from:
            received_qs = received_qs.filter(created_at__date__gte=date_from)
        if date_to:
            received_qs = received_qs.filter(created_at__date__lte=date_to)
        for r in received_qs.order_by('-created_at'):
            rows.append(_row(
                r.created_at.isoformat() if r.created_at else '',
                'received',
                r.name or f"Payment for Order #{r.order_id}",
                r.amount,
                r.id,
                r.restaurant_id,
                r.restaurant.name if r.restaurant else None,
            ))
        rows.sort(key=lambda x: x['date'], reverse=True)
        total_count = len(rows)
        start = (page - 1) * page_size
        paginated = rows[start:start + page_size]
        return {
            'stats': {
                'total_revenue': str(revenue),
                'total_expenses': '0',
                'total_orders': str(order_count),
                'net_profit': str(revenue),
            },
            'results': paginated,
            'pagination': {'page': page, 'page_size': page_size, 'total_count': total_count},
        }

    # --- Customer scope ---
    if customer_id is not None:
        order_qs = Order.objects.filter(customer_id=customer_id).select_related('restaurant')
        if date_from:
            order_qs = order_qs.filter(created_at__date__gte=date_from)
        if date_to:
            order_qs = order_qs.filter(created_at__date__lte=date_to)
        revenue = order_qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = order_qs.count()
        rows = []
        for o in order_qs.order_by('-created_at'):
            rows.append(_row(
                o.created_at.isoformat() if o.created_at else '',
                'order',
                f"Order #{o.id}",
                o.total,
                o.id,
                o.restaurant_id,
                o.restaurant.name if o.restaurant else None,
            ))
        received_qs = ReceivedRecord.objects.filter(customer_id=customer_id).select_related('order', 'restaurant')
        if date_from:
            received_qs = received_qs.filter(created_at__date__gte=date_from)
        if date_to:
            received_qs = received_qs.filter(created_at__date__lte=date_to)
        for r in received_qs.order_by('-created_at'):
            rows.append(_row(
                r.created_at.isoformat() if r.created_at else '',
                'received',
                r.name or f"Payment for Order #{r.order_id or ''}",
                r.amount,
                r.id,
                r.restaurant_id,
                r.restaurant.name if r.restaurant else None,
            ))
        rows.sort(key=lambda x: x['date'], reverse=True)
        total_count = len(rows)
        start = (page - 1) * page_size
        paginated = rows[start:start + page_size]
        return {
            'stats': {
                'total_revenue': str(revenue),
                'total_expenses': '0',
                'total_orders': str(order_count),
                'net_profit': str(revenue),
            },
            'results': paginated,
            'pagination': {'page': page, 'page_size': page_size, 'total_count': total_count},
        }

    # --- Owner / Manager / Super Admin: restaurant scope ---
    if restaurant_ids is not None and len(restaurant_ids) == 0:
        return {
            'stats': {
                'total_revenue': '0',
                'total_expenses': '0',
                'total_orders': '0',
                'net_profit': '0',
            },
            'results': [],
            'pagination': {'page': page, 'page_size': page_size, 'total_count': 0},
        }

    order_qs = Order.objects.all().select_related('restaurant')
    if restaurant_ids is not None:
        order_qs = order_qs.filter(restaurant_id__in=restaurant_ids)
    if date_from:
        order_qs = order_qs.filter(created_at__date__gte=date_from)
    if date_to:
        order_qs = order_qs.filter(created_at__date__lte=date_to)
    revenue = order_qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
    order_count = order_qs.count()

    expenses_qs = Expenses.objects.all().select_related('restaurant')
    purchase_qs = Purchase.objects.all().select_related('restaurant')
    paid_qs = PaidRecord.objects.all().select_related('restaurant')
    received_qs = ReceivedRecord.objects.all().select_related('restaurant', 'order')
    if restaurant_ids is not None:
        expenses_qs = expenses_qs.filter(restaurant_id__in=restaurant_ids)
        purchase_qs = purchase_qs.filter(restaurant_id__in=restaurant_ids)
        paid_qs = paid_qs.filter(restaurant_id__in=restaurant_ids)
        received_qs = received_qs.filter(restaurant_id__in=restaurant_ids)
    if date_from:
        expenses_qs = expenses_qs.filter(created_at__date__gte=date_from)
        purchase_qs = purchase_qs.filter(created_at__date__gte=date_from)
        paid_qs = paid_qs.filter(created_at__date__gte=date_from)
        received_qs = received_qs.filter(created_at__date__gte=date_from)
    if date_to:
        expenses_qs = expenses_qs.filter(created_at__date__lte=date_to)
        purchase_qs = purchase_qs.filter(created_at__date__lte=date_to)
        paid_qs = paid_qs.filter(created_at__date__lte=date_to)
        received_qs = received_qs.filter(created_at__date__lte=date_to)

    total_expenses = (
        (expenses_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0'))
        + (purchase_qs.aggregate(s=Sum('total'))['s'] or Decimal('0'))
        + (paid_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0'))
    )
    net = revenue - total_expenses

    rows = []
    for o in order_qs.order_by('-created_at'):
        rows.append(_row(
            o.created_at.isoformat() if o.created_at else '',
            'order',
            f"Order #{o.id}",
            o.total,
            o.id,
            o.restaurant_id,
            o.restaurant.name if o.restaurant else None,
        ))
    for r in received_qs.order_by('-created_at'):
        rows.append(_row(
            r.created_at.isoformat() if r.created_at else '',
            'received',
            r.name or f"Payment (Order #{r.order_id or '-'})",
            r.amount,
            r.id,
            r.restaurant_id,
            r.restaurant.name if r.restaurant else None,
        ))
    for p in paid_qs.order_by('-created_at'):
        rows.append(_row(
            p.created_at.isoformat() if p.created_at else '',
            'paid',
            p.name or "Payment out",
            -p.amount,
            p.id,
            p.restaurant_id,
            p.restaurant.name if p.restaurant else None,
        ))
    for e in expenses_qs.order_by('-created_at'):
        rows.append(_row(
            e.created_at.isoformat() if e.created_at else '',
            'expense',
            e.name or "Expense",
            -e.amount,
            e.id,
            e.restaurant_id,
            e.restaurant.name if e.restaurant else None,
        ))
    for p in purchase_qs.order_by('-created_at'):
        rows.append(_row(
            p.created_at.isoformat() if p.created_at else '',
            'purchase',
            f"Purchase #{p.id}",
            -p.total,
            p.id,
            p.restaurant_id,
            p.restaurant.name if p.restaurant else None,
        ))

    rows.sort(key=lambda x: x['date'], reverse=True)
    total_count = len(rows)
    start = (page - 1) * page_size
    paginated = rows[start:start + page_size]

    return {
        'stats': {
            'total_revenue': str(revenue),
            'total_expenses': str(total_expenses),
            'total_orders': str(order_count),
            'net_profit': str(net),
        },
        'results': paginated,
        'pagination': {'page': page, 'page_size': page_size, 'total_count': total_count},
    }


def _csv_response(data):
    """Return CSV HttpResponse from stats + results (same shape as JSON)."""
    import csv
    from io import StringIO
    rows = data.get('results', [])
    if not rows:
        buffer = StringIO()
        w = csv.writer(buffer)
        w.writerow(['date', 'type', 'description', 'amount', 'reference_id', 'restaurant_id', 'restaurant_name'])
        resp = HttpResponse(buffer.getvalue(), content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="transaction_history.csv"'
        return resp
    keys = list(rows[0].keys())
    buffer = StringIO()
    w = csv.DictWriter(buffer, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
    resp = HttpResponse(buffer.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = 'attachment; filename="transaction_history.csv"'
    return resp


# --- Role-scoped views (decorators applied in urls) ---


@require_http_methods(['GET'])
def super_admin_transaction_history(request):
    """All restaurants; requires super_admin_required in url."""
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    fmt = request.GET.get('format', '').lower()
    data = get_transaction_history_data(
        restaurant_ids=None,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if fmt == 'csv':
        return _csv_response(data)
    return JsonResponse(data)


def _get_owner_transactions_by_category(restaurant_ids, date_from=None, date_to=None, category=None, page=1, page_size=20):
    """Build paginated list from Transaction model with optional category filter; include trend by day."""
    from django.db.models import Sum
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), 100)
    qs = Transaction.objects.filter(restaurant_id__in=restaurant_ids).select_related('restaurant').order_by('-created_at')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if category:
        qs = qs.filter(category=category)
    total_count = qs.count()
    start = (page - 1) * page_size
    rows = []
    for t in qs[start:start + page_size]:
        rows.append({
            'date': t.created_at.isoformat() if t.created_at else None,
            'category': t.category or '',
            'amount': str(t.amount),
            'status': t.payment_status or '',
            'restaurant_id': t.restaurant_id,
            'restaurant_name': t.restaurant.name if t.restaurant_id and t.restaurant else None,
            'remarks': t.remarks or '',
            'transaction_type': t.transaction_type,
        })
    trend_qs = Transaction.objects.filter(restaurant_id__in=restaurant_ids).exclude(category='')
    if date_from:
        trend_qs = trend_qs.filter(created_at__date__gte=date_from)
    if date_to:
        trend_qs = trend_qs.filter(created_at__date__lte=date_to)
    if category:
        trend_qs = trend_qs.filter(category=category)
    trend_qs = trend_qs.annotate(day=TruncDate('created_at')).values('day', 'category').annotate(total=Sum('amount')).order_by('day')
    by_day = {}
    for row in trend_qs:
        day = row['day'].isoformat() if row.get('day') else ''
        if day not in by_day:
            by_day[day] = {'name': day[:10] if day else '', 'total': 0, 'by_category': {}}
        t = float(row.get('total') or 0)
        by_day[day]['total'] += t
        cat = row.get('category') or 'other'
        by_day[day]['by_category'][cat] = by_day[day]['by_category'].get(cat, 0) + t
    trend = list(sorted(by_day.values(), key=lambda x: x['name']))[-30:]
    return {
        'stats': {'total_count': total_count},
        'results': rows,
        'pagination': {'page': page, 'page_size': page_size, 'total_count': total_count},
        'trend': trend,
        'source': 'transactions',
    }


@require_http_methods(['GET'])
def owner_transaction_history(request):
    """Owner's restaurants; unified history or ?source=transactions&category= for Transaction model list."""
    rid = get_restaurant_ids(request)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    fmt = request.GET.get('format', '').lower()
    source = request.GET.get('source', '')
    category = request.GET.get('category', '').strip() or None
    if source == 'transactions':
        from datetime import datetime as _dt
        date_from_parsed = None
        date_to_parsed = None
        if date_from:
            try:
                date_from_parsed = _dt.strptime(date_from[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        if date_to:
            try:
                date_to_parsed = _dt.strptime(date_to[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        data = _get_owner_transactions_by_category(
            restaurant_ids=rid,
            date_from=date_from_parsed,
            date_to=date_to_parsed,
            category=category,
            page=page,
            page_size=page_size,
        )
        return JsonResponse(data)
    data = get_transaction_history_data(
        restaurant_ids=rid,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if fmt == 'csv':
        return _csv_response(data)
    return JsonResponse(data)


@require_http_methods(['GET'])
def manager_transaction_history(request):
    """Manager's assigned restaurants; requires auth + manager_required + manager_unlocked in url."""
    rid = get_restaurant_ids(request)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    fmt = request.GET.get('format', '').lower()
    data = get_transaction_history_data(
        restaurant_ids=rid,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if fmt == 'csv':
        return _csv_response(data)
    return JsonResponse(data)


@require_http_methods(['GET'])
def waiter_transaction_history(request):
    """Only orders/received where waiter_id = current staff; requires auth + waiter_required + waiter_unlocked in url."""
    staff_id = get_waiter_staff_id(request)
    if staff_id is None:
        from django.http import JsonResponse as J
        return J({'error': 'Waiter access required', 'stats': {}, 'results': [], 'pagination': {'page': 1, 'page_size': 20, 'total_count': 0}}, status=403)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    fmt = request.GET.get('format', '').lower()
    data = get_transaction_history_data(
        waiter_staff_id=staff_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if fmt == 'csv':
        return _csv_response(data)
    return JsonResponse(data)


@require_http_methods(['GET'])
def customer_transaction_history(request):
    """Only customer's orders/received; requires customer_auth_required in url."""
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden', 'stats': {}, 'results': [], 'pagination': {'page': 1, 'page_size': 20, 'total_count': 0}}, status=403)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    fmt = request.GET.get('format', '').lower()
    data = get_transaction_history_data(
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    if fmt == 'csv':
        return _csv_response(data)
    return JsonResponse(data)
