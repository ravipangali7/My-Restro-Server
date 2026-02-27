"""Super Admin restaurants list with stats, create, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Q, Count
from django.db.models.functions import TruncDate, TruncMonth

from core.models import (
    Restaurant, User, Order, OrderItem, Vendor, Transaction, Staff, OrderStatus,
    PaidRecord, ReceivedRecord, Purchase, Expenses, StockLog, Attendance,
    TransactionCategory, SuperSetting, PaymentStatus,
)
from core.utils import auth_required, image_url_for_request, get_restaurant_subscription_status
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code


def _parse_decimal(value, default=None):
    """Parse value to Decimal; empty string or invalid -> default (Decimal('0'))."""
    if default is None:
        default = Decimal('0')
    if value is None:
        return default
    s = str(value).strip()
    if s == '':
        return default
    try:
        return Decimal(s)
    except Exception:
        return default


def _parse_date(value):
    """Parse YYYY-MM-DD string to date or None."""
    if not value:
        return None
    s = str(value).strip()[:10]
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


def _validate_restaurant_body(body):
    """Return (None, None) if valid, else (JsonResponse with 400, None)."""
    tax = body.get('tax_percent')
    if tax is not None and str(tax).strip() != '':
        try:
            t = Decimal(str(tax).strip())
            if t < 0 or t > 100:
                return JsonResponse({'error': 'Tax percent must be between 0 and 100'}, status=400), None
        except Exception:
            return JsonResponse({'error': 'Invalid tax percent'}, status=400), None
    balance = body.get('balance')
    if balance is not None and str(balance).strip() != '':
        try:
            if Decimal(str(balance).strip()) < 0:
                return JsonResponse({'error': 'Balance cannot be negative'}, status=400), None
        except Exception:
            pass
    due_balance = body.get('due_balance')
    if due_balance is not None and str(due_balance).strip() != '':
        try:
            if Decimal(str(due_balance).strip()) < 0:
                return JsonResponse({'error': 'Due balance cannot be negative'}, status=400), None
        except Exception:
            pass
    sub_start = _parse_date(body.get('subscription_start'))
    sub_end = _parse_date(body.get('subscription_end'))
    if sub_start is not None and sub_end is not None and sub_end < sub_start:
        return JsonResponse({'error': 'Subscription end must be on or after subscription start'}, status=400), None
    return None, None


def _restaurant_to_dict(r, stats_extra=None, request=None):
    is_restaurant = getattr(r, 'is_restaurant', True)
    d = {
        'id': r.id,
        'user_id': r.user_id,
        'slug': r.slug,
        'name': r.name,
        'phone': r.phone or '',
        'country_code': getattr(r, 'country_code', '') or '',
        'email': getattr(r, 'email', '') or '',
        'logo': image_url_for_request(request, r.logo if getattr(r, 'logo', None) else None),
        'address': r.address or '',
        'tax_percent': str(r.tax_percent) if r.tax_percent is not None else None,
        'latitude': str(r.latitude) if r.latitude is not None else None,
        'longitude': str(r.longitude) if r.longitude is not None else None,
        'balance': str(r.balance),
        'due_balance': str(r.due_balance),
        'ug_api': r.ug_api or '',
        'esewa_merchant_id': getattr(r, 'esewa_merchant_id', '') or '',
        'subscription_start': r.subscription_start.isoformat() if r.subscription_start else None,
        'subscription_end': r.subscription_end.isoformat() if r.subscription_end else None,
        'is_open': r.is_open,
        'is_restaurant': is_restaurant,
        'subscription_status': get_restaurant_subscription_status(r.subscription_end, is_restaurant),
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None,
    }
    if stats_extra:
        d.update(stats_extra)
    return d


def _order_to_dict(o, include_items=False):
    """Minimal order dict for list (matches owner order list shape)."""
    d = {
        'id': o.id,
        'customer_id': o.customer_id,
        'restaurant_id': o.restaurant_id,
        'restaurant_name': o.restaurant.name if getattr(o, 'restaurant', None) else None,
        'table_id': o.table_id,
        'table_name': o.table.name if o.table else None,
        'table_number': o.table_number or '',
        'order_type': o.order_type,
        'status': o.status,
        'payment_status': o.payment_status or '',
        'payment_method': o.payment_method or '',
        'waiter_id': o.waiter_id,
        'waiter_name': o.waiter.user.name if o.waiter and getattr(o.waiter, 'user', None) else None,
        'total': str(o.total),
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'updated_at': o.updated_at.isoformat() if o.updated_at else None,
        'customer_name': o.customer.name if o.customer else None,
        'customer_phone': o.customer.phone if o.customer else None,
        'items_count': o.items.count(),
    }
    if include_items:
        d['items'] = [
            {
                'id': i.id,
                'product_name': getattr(i.product, 'name', None) or getattr(i.combo_set, 'name', None) or '—',
                'quantity': str(i.quantity),
                'total': str(i.total),
            }
            for i in o.items.select_related('product', 'combo_set').all()
        ]
    return d


@auth_required
@require_http_methods(['GET'])
def super_admin_restaurant_orders(request, pk):
    """GET super_admin restaurants/<pk>/orders/ — paginated orders for restaurant. Params: status, date_from, date_to, page, page_size."""
    r = get_object_or_404(Restaurant, pk=pk)
    qs = Order.objects.filter(restaurant=r).select_related('table', 'customer', 'waiter__user').prefetch_related('items').order_by('-created_at')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    status = (request.GET.get('status') or '').strip().lower()
    if status and status != 'all':
        if status == 'paid':
            qs = qs.filter(payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS])
        elif status == 'preparing':
            qs = qs.filter(status=OrderStatus.RUNNING)
        else:
            qs = qs.filter(status=status)
    total_count = qs.count()
    page = max(1, int(request.GET.get('page', 1)))
    page_size = max(1, min(100, int(request.GET.get('page_size', 20))))
    start = (page - 1) * page_size
    results = [_order_to_dict(o, include_items=True) for o in qs[start : start + page_size]]
    return JsonResponse({'count': total_count, 'results': results, 'page': page, 'page_size': page_size})


@auth_required
@require_http_methods(['GET'])
def super_admin_restaurant_check_slug(request):
    """GET ?slug=xxx&exclude_id=123 -> { available: true } if slug not taken (excluding pk 123)."""
    slug = (request.GET.get('slug') or '').strip()
    if not slug:
        return JsonResponse({'available': False})
    qs = Restaurant.objects.filter(slug=slug)
    exclude_id = request.GET.get('exclude_id')
    if exclude_id:
        try:
            qs = qs.exclude(pk=int(exclude_id))
        except (TypeError, ValueError):
            pass
    exists = qs.exists()
    return JsonResponse({'available': not exists})


@require_http_methods(['GET'])
def super_admin_restaurant_list(request):
    """List all restaurants with stats. Filter by search/date."""
    qs = Restaurant.objects.all().select_related('user')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(slug__icontains=search) | Q(phone__icontains=search)
        )
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    total = qs.count()
    active = qs.filter(is_open=True).count()
    inactive = qs.filter(is_open=False).count()
    kyc_pending = User.objects.filter(is_owner=True, kyc_status='pending').count()
    subscription_earnings = 0
    total_due = qs.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    due_blocked = 0
    stats = {
        'total': total,
        'active': active,
        'inactive': inactive,
        'kyc_pending': kyc_pending,
        'subscription_earnings': str(subscription_earnings),
        'total_due': str(total_due),
        'due_blocked': due_blocked,
    }
    results = []
    for r in qs.order_by('name')[:100]:
        rev = Order.objects.filter(restaurant=r).exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = Order.objects.filter(restaurant=r).count()
        staff_count = r.staffs.count()
        owner_name = getattr(r.user, 'name', '') or getattr(r.user, 'username', '') if r.user else ''
        results.append(_restaurant_to_dict(r, {
            'revenue': str(rev),
            'order_count': order_count,
            'staff_count': staff_count,
            'owner_name': owner_name,
        }, request=request))
    return JsonResponse({'stats': stats, 'results': results})


@require_http_methods(['GET'])
def super_admin_restaurant_detail(request, pk):
    r = get_object_or_404(Restaurant, pk=pk)
    data = _restaurant_to_dict(r, request=request)
    # Vendor financials for this restaurant
    vendor_agg = Vendor.objects.filter(restaurant=r).aggregate(
        to_pay=Sum('to_pay'), to_receive=Sum('to_receive')
    )
    data['vendor_to_pay'] = str(vendor_agg['to_pay'] or Decimal('0'))
    data['vendor_to_receive'] = str(vendor_agg['to_receive'] or Decimal('0'))
    # Recent transactions (no orders/menu)
    transactions = Transaction.objects.filter(restaurant=r).order_by('-created_at')[:50]
    data['transactions'] = [
        {
            'id': t.id,
            'amount': str(t.amount),
            'transaction_type': t.transaction_type,
            'category': t.category or '',
            'payment_status': t.payment_status or '',
            'created_at': t.created_at.isoformat() if t.created_at else None,
        }
        for t in transactions
    ]
    # Revenue analytics: time-bucketed order totals (last 30 days by day)
    from django.utils import timezone
    from datetime import timedelta
    start = timezone.now() - timedelta(days=30)
    daily = (
        Order.objects.filter(restaurant=r)
        .exclude(status=OrderStatus.REJECTED)
        .filter(created_at__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(value=Sum('total'))
        .order_by('day')
    )
    data['sales_data'] = [
        {'name': row['day'].isoformat() if row.get('day') else '', 'value': float(row.get('value') or 0), 'sales': float(row.get('value') or 0)}
        for row in daily
    ]
    # Restaurant owner (r.user)
    owner_user = r.user
    data['restaurant_owner'] = {
        'id': owner_user.id,
        'name': getattr(owner_user, 'name', '') or getattr(owner_user, 'username', ''),
        'phone': getattr(owner_user, 'phone', '') or '',
        'country_code': getattr(owner_user, 'country_code', '') or '',
        'image': image_url_for_request(request, getattr(owner_user, 'image', None)),
    } if owner_user else None
    # Staff list (managers, waiters)
    staff_list = Staff.objects.filter(restaurant=r).select_related('user')
    data['staff_list'] = [
        {
            'id': s.id,
            'user_id': s.user_id,
            'user_name': getattr(s.user, 'name', '') or getattr(s.user, 'username', ''),
            'designation': s.designation or '',
            'is_manager': s.is_manager,
            'is_waiter': s.is_waiter,
            'salary': str(s.salary) if s.salary is not None else '0',
            'to_pay': str(s.to_pay),
            'to_receive': str(s.to_receive),
        }
        for s in staff_list
    ]
    # Recent orders with items
    recent_orders_qs = Order.objects.filter(restaurant=r).order_by('-created_at')[:20]
    data['recent_orders'] = []
    for o in recent_orders_qs:
        items = OrderItem.objects.filter(order=o).select_related('product', 'product_variant', 'combo_set')
        data['recent_orders'].append({
            'id': o.id,
            'total': str(o.total),
            'status': o.status,
            'payment_status': o.payment_status or '',
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'items': [
                {'id': i.id, 'product_name': getattr(i.product, 'name', None) or getattr(i.combo_set, 'name', None) or '—', 'quantity': str(i.quantity), 'total': str(i.total)}
                for i in items
            ],
        })
    # PaidRecord / ReceivedRecord (recent)
    paid = PaidRecord.objects.filter(restaurant=r).order_by('-created_at')[:30]
    data['paid_records'] = [{'id': p.id, 'name': p.name, 'amount': str(p.amount), 'created_at': p.created_at.isoformat() if p.created_at else None} for p in paid]
    received = ReceivedRecord.objects.filter(restaurant=r).order_by('-created_at')[:30]
    data['received_records'] = [{'id': rec.id, 'name': rec.name, 'amount': str(rec.amount), 'order_id': rec.order_id, 'created_at': rec.created_at.isoformat() if rec.created_at else None} for rec in received]
    # Stock summary (recent stock logs)
    stock_logs = StockLog.objects.filter(restaurant=r).select_related('raw_material').order_by('-created_at')[:50]
    data['stock_logs'] = [{'id': sl.id, 'type': sl.type, 'quantity': str(sl.quantity), 'raw_material_name': sl.raw_material.name if sl.raw_material_id else '—', 'created_at': sl.created_at.isoformat() if sl.created_at else None} for sl in stock_logs]
    # Purchases / Expenses totals
    purchases_total = Purchase.objects.filter(restaurant=r).aggregate(s=Sum('total'))['s'] or Decimal('0')
    expenses_total = Expenses.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['purchases_total'] = str(purchases_total)
    data['expenses_total'] = str(expenses_total)
    # Transaction IN / OUT for pie
    tx_in = Transaction.objects.filter(restaurant=r, transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    tx_out = Transaction.objects.filter(restaurant=r, transaction_type='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['transaction_in_total'] = str(tx_in)
    data['transaction_out_total'] = str(tx_out)
    # Monthly revenue (bar chart) - last 12 months
    from django.utils import timezone
    from datetime import timedelta
    start_month = timezone.now() - timedelta(days=365)
    monthly = (
        Order.objects.filter(restaurant=r)
        .exclude(status=OrderStatus.REJECTED)
        .filter(created_at__gte=start_month)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(value=Sum('total'))
        .order_by('month')
    )
    data['monthly_sales'] = [{'name': row['month'].strftime('%Y-%m') if row.get('month') else '', 'value': float(row.get('value') or 0)} for row in monthly]
    # Attendance summary per staff (last 30 days)
    from datetime import timedelta as td
    start_date = timezone.now().date() - td(days=30)
    att_qs = Attendance.objects.filter(restaurant=r, date__gte=start_date).values('staff_id').annotate(
        present=Count('id', filter=Q(status='present')),
        leave=Count('id', filter=Q(status='leave')),
        absent=Count('id', filter=Q(status='absent')),
    )
    data['attendance_summary'] = list(att_qs)

    # Stats summary (single source for cards)
    order_count = Order.objects.filter(restaurant=r).count()
    revenue = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED).aggregate(s=Sum('total'))['s'] or Decimal('0')
    paid_total = PaidRecord.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    received_total = ReceivedRecord.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['stats'] = {
        'total_orders': order_count,
        'revenue': str(revenue),
        'due_balance': str(r.due_balance),
        'balance': str(r.balance),
        'vendor_to_pay': data['vendor_to_pay'],
        'vendor_to_receive': data['vendor_to_receive'],
        'staff_count': len(staff_list),
        'paid_total': str(paid_total),
        'received_total': str(received_total),
    }

    # Transaction breakdown by category (this restaurant only)
    breakdown = (
        Transaction.objects.filter(restaurant=r)
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('category')
    )
    data['transaction_breakdown_by_category'] = [
        {'category': row['category'] or 'other', 'total': str(row['total'] or Decimal('0'))}
        for row in breakdown
    ]

    # Balance flow: daily in/out for last 30 days
    start_flow = timezone.now() - timedelta(days=30)
    flow_qs = (
        Transaction.objects.filter(restaurant=r, created_at__gte=start_flow)
        .annotate(day=TruncDate('created_at'))
        .values('day', 'transaction_type')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    by_day = {}
    for row in flow_qs:
        day = row['day'].isoformat() if row.get('day') else ''
        if day not in by_day:
            by_day[day] = {'name': day, 'in': 0, 'out': 0}
        t = float(row.get('total') or 0)
        if row.get('transaction_type') == 'in':
            by_day[day]['in'] = t
        else:
            by_day[day]['out'] = t
    data['balance_flow'] = list(sorted(by_day.values(), key=lambda x: x['name']))

    # SuperSetting impact (read-only snapshot)
    ss = SuperSetting.objects.first()
    data['super_setting_impact'] = {
        'per_transaction_fee': str(ss.per_transaction_fee) if ss and ss.per_transaction_fee is not None else '0',
        'due_threshold': str(ss.due_threshold) if ss and ss.due_threshold is not None else '0',
        'subscription_fee_per_month': str(ss.subscription_fee_per_month) if ss and ss.subscription_fee_per_month is not None else '0',
        'per_qr_stand_price': str(ss.per_qr_stand_price) if ss and ss.per_qr_stand_price is not None else '0',
    } if ss else {'per_transaction_fee': '0', 'due_threshold': '0', 'subscription_fee_per_month': '0', 'per_qr_stand_price': '0'}

    return JsonResponse(data)


def _get_request_body(request):
    """Parse body from POST form or JSON. Returns (dict, logo_file). Never reads request.body when POST/FILES present."""
    if request.POST or request.FILES:
        body = dict(request.POST.items()) if request.POST else {}
        for k, v in body.items():
            if isinstance(v, list) and len(v) == 1:
                body[k] = v[0]
        return body, request.FILES.get('logo') if request.FILES else None
    content_type = (request.META.get('CONTENT_TYPE') or getattr(request, 'content_type', None) or '').lower()
    if 'application/json' in content_type and request.body:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = {}
    else:
        body = {}
    return body, None


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_restaurant_create(request):
    body, logo_file = _get_request_body(request)
    err_resp, _ = _validate_restaurant_body(body)
    if err_resp:
        return err_resp
    from core.models import User as UserModel
    user_id = body.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'user_id must be an integer'}, status=400)
    user = UserModel.objects.filter(pk=user_id).first()
    if not user:
        return JsonResponse({'error': 'User not found'}, status=404)
    if not getattr(user, 'is_owner', False):
        return JsonResponse({'error': 'User must be an owner'}, status=400)
    slug = (body.get('slug') or '').strip()
    name = (body.get('name') or '').strip()
    if not slug or not name:
        return JsonResponse({'error': 'slug and name required'}, status=400)
    if Restaurant.objects.filter(slug=slug).exists():
        return JsonResponse({'error': 'slug already exists'}, status=400)
    country_code = normalize_country_code((body.get('country_code') or '').strip())
    if country_code and country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
        }, status=400)
    tax_percent = body.get('tax_percent')
    if tax_percent is not None and str(tax_percent).strip() != '':
        try:
            tax_percent = Decimal(str(tax_percent).strip())
        except Exception:
            tax_percent = None
    else:
        tax_percent = None
    lat = body.get('latitude')
    lon = body.get('longitude')
    if lat is not None and str(lat).strip() != '':
        try:
            lat = Decimal(str(lat).strip())
        except Exception:
            lat = None
    else:
        lat = None
    if lon is not None and str(lon).strip() != '':
        try:
            lon = Decimal(str(lon).strip())
        except Exception:
            lon = None
    else:
        lon = None
    r = Restaurant(
        user=user,
        slug=slug,
        name=name,
        phone=body.get('phone', ''),
        country_code=country_code,
        email=(body.get('email') or '').strip() or '',
        address=body.get('address', ''),
        tax_percent=tax_percent,
        latitude=lat,
        longitude=lon,
        balance=_parse_decimal(body.get('balance')),
        due_balance=_parse_decimal(body.get('due_balance')),
        ug_api=body.get('ug_api') or '',
        esewa_merchant_id=(body.get('esewa_merchant_id') or '').strip() or None,
        subscription_start=_parse_date(body.get('subscription_start')),
        subscription_end=_parse_date(body.get('subscription_end')),
        is_open=str(body.get('is_open', True)).lower() in ('true', '1', 'yes'),
        is_restaurant=str(body.get('is_restaurant', True)).lower() not in ('false', '0', 'no'),
    )
    if logo_file:
        r.logo = logo_file
    r.save()
    return JsonResponse(_restaurant_to_dict(r, request=request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def super_admin_restaurant_update(request, pk):
    r = get_object_or_404(Restaurant, pk=pk)
    body, logo_file = _get_request_body(request)
    err_resp, _ = _validate_restaurant_body(body)
    if err_resp:
        return err_resp
    if logo_file:
        r.logo = logo_file
    # Only update logo when new file provided; otherwise keep existing
    for key in ('slug', 'name', 'phone', 'address', 'ug_api', 'is_open', 'email', 'esewa_merchant_id'):
        if key in body:
            val = body[key]
            if key == 'is_open':
                val = str(val).lower() in ('true', '1', 'yes')
            elif key in ('email', 'esewa_merchant_id'):
                val = (val or '').strip() or ('' if key == 'email' else None)
            setattr(r, key, val)
    if 'is_restaurant' in body:
        r.is_restaurant = str(body['is_restaurant']).lower() not in ('false', '0', 'no')
    if 'country_code' in body:
        new_cc = normalize_country_code(str(body.get('country_code', '')).strip())
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
            }, status=400)
        r.country_code = new_cc
    if 'tax_percent' in body:
        v = body['tax_percent']
        if v is not None and str(v).strip() != '':
            try:
                r.tax_percent = Decimal(str(v).strip())
            except Exception:
                pass
        else:
            r.tax_percent = None
    if 'latitude' in body:
        v = body['latitude']
        if v is not None and str(v).strip() != '':
            try:
                r.latitude = Decimal(str(v).strip())
            except Exception:
                pass
        else:
            r.latitude = None
    if 'longitude' in body:
        v = body['longitude']
        if v is not None and str(v).strip() != '':
            try:
                r.longitude = Decimal(str(v).strip())
            except Exception:
                pass
        else:
            r.longitude = None
    if 'balance' in body:
        r.balance = _parse_decimal(body['balance'])
    if 'due_balance' in body:
        r.due_balance = _parse_decimal(body['due_balance'])
    if 'subscription_start' in body:
        r.subscription_start = _parse_date(body['subscription_start'])
    if 'subscription_end' in body:
        r.subscription_end = _parse_date(body['subscription_end'])
    # Slug uniqueness: exclude current pk
    if 'slug' in body and body.get('slug'):
        new_slug = str(body['slug']).strip()
        if new_slug and Restaurant.objects.filter(slug=new_slug).exclude(pk=r.pk).exists():
            return JsonResponse({'error': 'slug already exists'}, status=400)
    r.save()
    return JsonResponse(_restaurant_to_dict(r, request=request))


@auth_required
@require_http_methods(['DELETE'])
def super_admin_restaurant_delete(request, pk):
    r = get_object_or_404(Restaurant, pk=pk)
    r.delete()
    return JsonResponse({'success': True}, status=200)
