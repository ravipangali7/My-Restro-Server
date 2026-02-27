"""Function-based views for owner restaurant CRUD and list."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from core.models import (
    Restaurant,
    Order,
    OrderItem,
    OrderStatus,
    Vendor,
    Transaction,
    TransactionCategory,
    Staff,
    PaidRecord,
    ReceivedRecord,
    Purchase,
    Expenses,
    StockLog,
    Attendance,
    SuperSetting,
)
from core.utils import get_restaurant_ids, auth_required, is_owner_only, image_url_for_request, get_restaurant_subscription_status
from core.permissions import is_manager
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code


def _parse_date(body_value):
    """Parse YYYY-MM-DD from body value to date or None."""
    if not body_value:
        return None
    s = str(body_value).strip()[:10]
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


def _validate_restaurant_body(body):
    """Return (None, None) if valid, else (JsonResponse 400, None)."""
    tax = body.get('tax_percent')
    if tax is not None and str(tax).strip() != '':
        try:
            t = Decimal(str(tax).strip())
            if t < 0 or t > 100:
                return JsonResponse({'error': 'Tax percent must be between 0 and 100'}, status=400), None
        except Exception:
            return JsonResponse({'error': 'Invalid tax percent'}, status=400), None
    if body.get('balance') is not None and str(body.get('balance')).strip() != '':
        try:
            if Decimal(str(body['balance']).strip()) < 0:
                return JsonResponse({'error': 'Balance cannot be negative'}, status=400), None
        except Exception:
            pass
    if body.get('due_balance') is not None and str(body.get('due_balance')).strip() != '':
        try:
            if Decimal(str(body['due_balance']).strip()) < 0:
                return JsonResponse({'error': 'Due balance cannot be negative'}, status=400), None
        except Exception:
            pass
    sub_start = _parse_date(body.get('subscription_start'))
    sub_end = _parse_date(body.get('subscription_end'))
    if sub_start is not None and sub_end is not None and sub_end < sub_start:
        return JsonResponse({'error': 'Subscription end must be on or after subscription start'}, status=400), None
    return None, None


def _restaurant_to_dict(r, request=None):
    is_restaurant = getattr(r, 'is_restaurant', True)
    return {
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
        'subscription_start': str(r.subscription_start) if r.subscription_start else None,
        'subscription_end': str(r.subscription_end) if r.subscription_end else None,
        'is_open': r.is_open,
        'is_restaurant': is_restaurant,
        'subscription_status': get_restaurant_subscription_status(r.subscription_end, is_restaurant),
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def owner_restaurant_check_slug(request):
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


@auth_required
@require_http_methods(['GET'])
def owner_restaurant_list(request):
    """List restaurants (model-aligned keys). Scope by owner's restaurants if auth."""
    restaurant_ids = get_restaurant_ids(request)
    qs = Restaurant.objects.select_related('user').order_by('name')
    if restaurant_ids and not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(id__in=restaurant_ids)
    data = [_restaurant_to_dict(r, request=request) for r in qs]
    return JsonResponse({'results': data})


@auth_required
@require_http_methods(['GET'])
def owner_restaurant_detail(request, pk):
    """Retrieve single restaurant (basic). Use ?deep=1 or /report/ for full deep relation."""
    r = get_object_or_404(Restaurant, pk=pk)
    restaurant_ids = get_restaurant_ids(request)
    if restaurant_ids and r.id not in restaurant_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse(
            {'error': 'Forbidden', 'detail': 'Restaurant not in your scope', 'locked': False},
            status=403,
        )
    if request.GET.get('deep') == '1':
        return JsonResponse(_owner_restaurant_deep_report(r, request))
    return JsonResponse(_restaurant_to_dict(r, request=request))


def _owner_restaurant_deep_report(r, request=None):
    """Build deep relation report for one restaurant (same shape as super_admin detail)."""
    data = _restaurant_to_dict(r, request=request)
    today = timezone.now().date()
    data['subscription_active'] = r.subscription_end is not None and r.subscription_end >= today

    vendor_agg = Vendor.objects.filter(restaurant=r).aggregate(
        to_pay=Sum('to_pay'), to_receive=Sum('to_receive')
    )
    data['vendor_to_pay'] = str(vendor_agg['to_pay'] or Decimal('0'))
    data['vendor_to_receive'] = str(vendor_agg['to_receive'] or Decimal('0'))

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

    owner_user = r.user
    data['restaurant_owner'] = {
        'id': owner_user.id,
        'name': getattr(owner_user, 'name', '') or getattr(owner_user, 'username', ''),
        'phone': getattr(owner_user, 'phone', '') or '',
        'country_code': getattr(owner_user, 'country_code', '') or '',
        'image': image_url_for_request(request, getattr(owner_user, 'image', None)),
    } if owner_user else None

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

    paid = PaidRecord.objects.filter(restaurant=r).order_by('-created_at')[:30]
    data['paid_records'] = [{'id': p.id, 'name': p.name, 'amount': str(p.amount), 'created_at': p.created_at.isoformat() if p.created_at else None} for p in paid]
    received = ReceivedRecord.objects.filter(restaurant=r).order_by('-created_at')[:30]
    data['received_records'] = [{'id': rec.id, 'name': rec.name, 'amount': str(rec.amount), 'order_id': rec.order_id, 'created_at': rec.created_at.isoformat() if rec.created_at else None} for rec in received]

    stock_logs = StockLog.objects.filter(restaurant=r).select_related('raw_material').order_by('-created_at')[:50]
    data['stock_logs'] = [{'id': sl.id, 'type': sl.type, 'quantity': str(sl.quantity), 'raw_material_name': sl.raw_material.name if sl.raw_material_id else '—', 'created_at': sl.created_at.isoformat() if sl.created_at else None} for sl in stock_logs]

    purchases_total = Purchase.objects.filter(restaurant=r).aggregate(s=Sum('total'))['s'] or Decimal('0')
    expenses_total = Expenses.objects.filter(restaurant=r).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['purchases_total'] = str(purchases_total)
    data['expenses_total'] = str(expenses_total)

    tx_in = Transaction.objects.filter(restaurant=r, transaction_type='in').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    tx_out = Transaction.objects.filter(restaurant=r, transaction_type='out').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['transaction_in_total'] = str(tx_in)
    data['transaction_out_total'] = str(tx_out)

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

    start_date = timezone.now().date() - timedelta(days=30)
    att_qs = Attendance.objects.filter(restaurant=r, date__gte=start_date).values('staff_id').annotate(
        present=Count('id', filter=Q(status='present')),
        leave=Count('id', filter=Q(status='leave')),
        absent=Count('id', filter=Q(status='absent')),
    )
    data['attendance_summary'] = list(att_qs)

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

    tx_fee_total = Transaction.objects.filter(restaurant=r, category=TransactionCategory.TRANSACTION_FEE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    whatsapp_total = Transaction.objects.filter(restaurant=r, category=TransactionCategory.WHATSAPP_USAGE).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    data['transaction_fee_total'] = str(tx_fee_total)
    data['whatsapp_usage_total'] = str(whatsapp_total)

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

    ss = SuperSetting.objects.first()
    data['super_setting_impact'] = {
        'per_transaction_fee': str(ss.per_transaction_fee) if ss and ss.per_transaction_fee is not None else '0',
        'due_threshold': str(ss.due_threshold) if ss and ss.due_threshold is not None else '0',
        'subscription_fee_per_month': str(ss.subscription_fee_per_month) if ss and ss.subscription_fee_per_month is not None else '0',
        'per_qr_stand_price': str(ss.per_qr_stand_price) if ss and ss.per_qr_stand_price is not None else '0',
    } if ss else {'per_transaction_fee': '0', 'due_threshold': '0', 'subscription_fee_per_month': '0', 'per_qr_stand_price': '0'}

    from core.models import QrStandOrder
    qr_orders = list(QrStandOrder.objects.filter(restaurant=r).order_by('-created_at')[:20].values('id', 'total', 'quantity', 'payment_status', 'created_at'))
    for q in qr_orders:
        q['total'] = str(q['total'])
        q['quantity'] = str(q['quantity']) if q.get('quantity') is not None else '0'
        q['created_at'] = q['created_at'].isoformat() if q.get('created_at') else None
    data['qr_stand_orders'] = qr_orders

    return data


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_restaurant_create(request):
    """Create restaurant. JSON: slug, name, phone?, address?, ug_api?, is_open?, email?, tax_percent?, latitude?, longitude?, esewa_merchant_id?, is_restaurant?, etc."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    err_resp, _ = _validate_restaurant_body(body)
    if err_resp:
        return err_resp
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
    user = request.user
    if not getattr(user, 'is_owner', False) and not getattr(user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
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
        phone=body.get('phone', '') or '',
        country_code=country_code,
        email=(body.get('email') or '').strip() or '',
        address=body.get('address', '') or '',
        tax_percent=tax_percent,
        latitude=lat,
        longitude=lon,
        ug_api=body.get('ug_api') or None,
        esewa_merchant_id=(body.get('esewa_merchant_id') or '').strip() or None,
        is_open=bool(body.get('is_open', True)),
        is_restaurant=bool(body.get('is_restaurant', True)),
    )
    if body.get('balance') is not None:
        try:
            b = Decimal(str(body['balance']))
            if b >= 0:
                r.balance = b
        except Exception:
            pass
    if body.get('due_balance') is not None:
        try:
            d = Decimal(str(body['due_balance']))
            if d >= 0:
                r.due_balance = d
        except Exception:
            pass
    r.subscription_start = _parse_date(body.get('subscription_start'))
    r.subscription_end = _parse_date(body.get('subscription_end'))
    r.save()
    return JsonResponse(_restaurant_to_dict(r, request=request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_restaurant_update(request, pk):
    """Update restaurant."""
    r = get_object_or_404(Restaurant, pk=pk)
    restaurant_ids = get_restaurant_ids(request)
    if restaurant_ids and r.id not in restaurant_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Manager can only update is_open and basic info (name, phone, address); cannot change is_restaurant
    if is_manager(request.user) and not getattr(request.user, 'is_superuser', False):
        if 'is_open' in body:
            r.is_open = bool(body['is_open'])
        if 'name' in body:
            r.name = str(body['name']).strip() or r.name
        if 'phone' in body:
            r.phone = str(body.get('phone', ''))
        if 'address' in body:
            r.address = str(body.get('address', ''))
        r.save()
        return JsonResponse(_restaurant_to_dict(r, request=request))

    err_resp, _ = _validate_restaurant_body(body)
    if err_resp:
        return err_resp

    if 'name' in body:
        r.name = str(body['name']).strip() or r.name
    if 'phone' in body:
        r.phone = str(body.get('phone', ''))
    if 'email' in body:
        r.email = (body.get('email') or '').strip() or ''
    if 'country_code' in body:
        new_cc = normalize_country_code(str(body.get('country_code', '')).strip())
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only 91 (India) and 977 (Nepal) are allowed.'
            }, status=400)
        r.country_code = new_cc
    if 'address' in body:
        r.address = str(body.get('address', ''))
    if 'ug_api' in body:
        r.ug_api = body.get('ug_api') or None
    if 'esewa_merchant_id' in body:
        r.esewa_merchant_id = (body.get('esewa_merchant_id') or '').strip() or None
    if 'is_open' in body:
        r.is_open = bool(body['is_open'])
    if 'is_restaurant' in body:
        r.is_restaurant = bool(body['is_restaurant'])
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
        try:
            b = Decimal(str(body['balance']))
            if b >= 0:
                r.balance = b
        except Exception:
            pass
    if 'due_balance' in body:
        try:
            d = Decimal(str(body['due_balance']))
            if d >= 0:
                r.due_balance = d
        except Exception:
            pass
    if 'subscription_start' in body:
        r.subscription_start = _parse_date(body['subscription_start'])
    if 'subscription_end' in body:
        r.subscription_end = _parse_date(body['subscription_end'])
    if 'slug' in body and body.get('slug'):
        new_slug = str(body['slug']).strip()
        if new_slug and Restaurant.objects.filter(slug=new_slug).exclude(pk=r.pk).exists():
            return JsonResponse({'error': 'slug already exists'}, status=400)
        if new_slug:
            r.slug = new_slug
    r.save()
    return JsonResponse(_restaurant_to_dict(r, request=request))


@auth_required
@require_http_methods(['DELETE'])
def owner_restaurant_delete(request, pk):
    """Delete restaurant. Owners are not allowed to delete (manager/superuser only)."""
    if is_owner_only(request):
        return JsonResponse({'detail': 'Delete not allowed for Owner'}, status=403)
    r = get_object_or_404(Restaurant, pk=pk)
    restaurant_ids = get_restaurant_ids(request)
    if restaurant_ids and r.id not in restaurant_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    r.delete()
    return JsonResponse({'success': True}, status=200)
