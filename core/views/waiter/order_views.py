"""Waiter orders: list (only where waiter_id=current waiter staff), detail, update, create. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from django.db.models import Q

from core.models import Order, OrderItem, OrderStatus, OrderType, PaymentStatus, Customer, Delivery
from core.payment_qr import generate_esewa_qr_png
from core.utils import get_waiter_staff_id, paginate_queryset, parse_date
from core.permissions import get_waiter_restaurant
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code
from core.invoice_utils import get_invoice_extras

# Waiter may only move: pending -> accepted -> running -> ready -> served (cannot set rejected)
WAITER_ALLOWED_NEXT_STATUS = {
    OrderStatus.PENDING: [OrderStatus.ACCEPTED],
    OrderStatus.ACCEPTED: [OrderStatus.RUNNING],
    OrderStatus.RUNNING: [OrderStatus.READY],
    OrderStatus.READY: [OrderStatus.SERVED],
    OrderStatus.SERVED: [],
    OrderStatus.REJECTED: [],
}


def _order_to_dict(o, include_items=False, request=None):
    rest = getattr(o, 'restaurant', None)
    d = {
        'id': o.id,
        'customer_id': o.customer_id,
        'restaurant_id': o.restaurant_id,
        'restaurant_name': rest.name if rest else None,
        'restaurant_address': getattr(rest, 'address', None) or '' if rest else '',
        'restaurant_phone': getattr(rest, 'phone', None) or '' if rest else '',
        'table_id': o.table_id,
        'table_name': o.table.name if o.table else None,
        'table_number': o.table_number or '',
        'order_type': o.order_type,
        'address': o.address or '',
        'status': o.status,
        'payment_status': o.payment_status,
        'payment_method': o.payment_method or '',
        'waiter_id': o.waiter_id,
        'waiter_name': (o.waiter.user.get_full_name() or o.waiter.user.username) if o.waiter and getattr(o.waiter, 'user', None) else None,
        'customer_name': o.customer.name if getattr(o, 'customer', None) and o.customer else None,
        'customer_phone': o.customer.phone if getattr(o, 'customer', None) and o.customer else None,
        'people_for': o.people_for,
        'total': str(o.total),
        'service_charge': str(o.service_charge) if o.service_charge is not None else None,
        'discount': str(o.discount) if o.discount is not None else None,
        'transaction_reference': o.transaction_reference or '',
        'reject_reason': o.reject_reason or '',
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'updated_at': o.updated_at.isoformat() if o.updated_at else None,
    }
    if include_items:
        items_qs = o.items.select_related('product', 'product_variant', 'combo_set').all()
        d['items'] = []
        for i in items_qs:
            item_dict = {
                'id': i.id,
                'product_id': i.product_id,
                'product_variant_id': i.product_variant_id,
                'combo_set_id': i.combo_set_id,
                'price': str(i.price),
                'quantity': str(i.quantity),
                'total': str(i.total),
                'product_name': None,
                'product_image': None,
            }
            if i.combo_set_id and i.combo_set:
                item_dict['product_name'] = i.combo_set.name
                if getattr(i.combo_set, 'image', None) and i.combo_set.image:
                    item_dict['product_image'] = i.combo_set.image.url
                    if request:
                        item_dict['product_image'] = request.build_absolute_uri(item_dict['product_image'])
            elif i.product_id and i.product:
                item_dict['product_name'] = i.product.name
                if getattr(i.product, 'image', None) and i.product.image:
                    item_dict['product_image'] = i.product.image.url
                    if request:
                        item_dict['product_image'] = request.build_absolute_uri(item_dict['product_image'])
            d['items'].append(item_dict)
    return d


@require_http_methods(['GET'])
def waiter_order_list(request):
    from django.db.models import Sum

    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'stats': {}, 'results': [], 'pagination': {'page': 1, 'page_size': 20, 'total_count': 0}})
    qs = Order.objects.filter(waiter_id=staff_id).select_related('table', 'customer').prefetch_related('items')
    start_date = parse_date(request.GET.get('start_date') or request.GET.get('date_from'))
    end_date = parse_date(request.GET.get('end_date') or request.GET.get('date_to'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(table__name__icontains=search)
            | Q(table_number__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(customer__phone__icontains=search)
        )
    status_filter = request.GET.get('status', '').strip().lower()
    new_only = request.GET.get('new_only', '').strip().lower() in ('1', 'true', 'yes')
    if status_filter == 'pending':
        qs = qs.filter(status=OrderStatus.PENDING)
    elif new_only:
        qs = qs.filter(status__in=(OrderStatus.PENDING, OrderStatus.ACCEPTED))
    total_revenue = qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
    stats = {
        'total': qs.count(),
        'pending': qs.filter(status=OrderStatus.PENDING).count(),
        'running': qs.filter(status=OrderStatus.RUNNING).count(),
        'ready': qs.filter(status=OrderStatus.READY).count(),
        'served': qs.filter(status=OrderStatus.SERVED).count(),
        'rejected': qs.filter(status=OrderStatus.REJECTED).count(),
        'total_revenue': str(total_revenue),
    }
    qs_paged, pagination = paginate_queryset(qs.order_by('-created_at'), request, default_page_size=20)
    results = [_order_to_dict(o) for o in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@require_http_methods(['GET'])
def waiter_order_new_count(request):
    """GET /api/waiter/orders/new-count/ — count of pending orders for badge."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'count': 0})
    count = Order.objects.filter(
        waiter_id=staff_id, status=OrderStatus.PENDING
    ).count()
    return JsonResponse({'count': count})


@require_http_methods(['GET'])
def waiter_order_detail(request, pk):
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(
        Order.objects.select_related('table', 'customer', 'restaurant', 'waiter__user').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.waiter_id != staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    d = _order_to_dict(o, include_items=True, request=request)
    d.update(get_invoice_extras(o))
    for i, it in enumerate(d.get('items', []), 1):
        it['sn'] = i
        it.setdefault('item_name', it.get('product_name'))
    return JsonResponse(d)


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
def waiter_order_update(request, pk):
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(Order.objects.select_related('restaurant'), pk=pk)
    if o.waiter_id != staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'status' in body:
        new_status = body['status']
        if new_status not in (
            OrderStatus.PENDING,
            OrderStatus.ACCEPTED,
            OrderStatus.RUNNING,
            OrderStatus.READY,
            OrderStatus.SERVED,
        ):
            return JsonResponse({'error': 'Invalid status'}, status=400)
        if new_status == OrderStatus.REJECTED:
            return JsonResponse({'error': 'Waiter cannot reject orders'}, status=400)
        allowed_next = WAITER_ALLOWED_NEXT_STATUS.get(o.status, [])
        if new_status not in allowed_next:
            return JsonResponse(
                {'error': f'Invalid transition from {o.status} to {new_status}'},
                status=400,
            )
        o.status = new_status
        if o.status == OrderStatus.ACCEPTED and o.order_type == OrderType.DELIVERY:
            Delivery.objects.get_or_create(
                order=o,
                defaults={
                    'delivery_status': 'accepted',
                    'pickup_lat': o.restaurant.latitude if getattr(o.restaurant, 'latitude', None) else None,
                    'pickup_lon': o.restaurant.longitude if getattr(o.restaurant, 'longitude', None) else None,
                    'delivery_lat': o.delivery_lat,
                    'delivery_lon': o.delivery_lon,
                }
            )
    if 'payment_status' in body:
        o.payment_status = body['payment_status']
    if 'transaction_reference' in body:
        o.transaction_reference = (body.get('transaction_reference') or '').strip() or None
    if 'discount' in body:
        try:
            o.discount = Decimal(str(body['discount'])) if body.get('discount') not in (None, '') else None
        except Exception:
            pass
    o.save()
    from core.order_notify import notify_order_update
    notify_order_update(o)
    return JsonResponse(_order_to_dict(o, include_items=True, request=request))


@csrf_exempt
@require_http_methods(['POST'])
def waiter_order_create(request):
    """
    Create order. Waiter and restaurant are auto-set from request.user.staff.
    Body: customer_name, country_code, customer_phone, payment_method, total; optional: table_id, order_type, service_charge, items.
    Do not pass restaurant_id or waiter_id (ignored for security).
    """
    restaurant = get_waiter_restaurant(request)
    if not restaurant:
        return JsonResponse({'error': 'No restaurant assigned'}, status=403)
    if not getattr(restaurant, 'is_restaurant', True):
        return JsonResponse({'error': 'Restaurant is inactive'}, status=403)
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if body.get('restaurant_id') is not None or body.get('waiter_id') is not None:
        return JsonResponse({'error': 'restaurant_id and waiter_id are set by the server'}, status=400)

    payment_method = (body.get('payment_method') or '').strip()
    if not payment_method:
        return JsonResponse({'error': 'payment_method required'}, status=400)

    customer_id = body.get('customer_id')
    if not customer_id:
        name = (body.get('customer_name') or '').strip()
        phone = (body.get('customer_phone') or '').strip()
        country_code = normalize_country_code((body.get('country_code') or '').strip())
        if not name:
            return JsonResponse({'error': 'customer_name required'}, status=400)
        if not phone:
            return JsonResponse({'error': 'customer_phone (phone) required'}, status=400)
        if not country_code:
            return JsonResponse({'error': 'country_code required'}, status=400)
        if country_code not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({'error': 'Invalid country_code'}, status=400)
        customer, _ = Customer.objects.get_or_create(
            phone=phone,
            defaults={'name': name, 'country_code': country_code}
        )
        customer_id = customer.id

    total = Decimal(str(body.get('total', 0)))
    service_charge_raw = body.get('service_charge')
    service_charge = Decimal(str(service_charge_raw)) if service_charge_raw not in (None, '') else Decimal('10')
    table_number_val = (body.get('table_number') or '').strip() or None

    order = Order(
        restaurant=restaurant,
        customer_id=customer_id,
        table_id=body.get('table_id') or None,
        table_number=table_number_val,
        order_type=body.get('order_type', 'table'),
        address=body.get('address') or '',
        status=body.get('status', OrderStatus.PENDING),
        payment_status=body.get('payment_status', PaymentStatus.PENDING),
        payment_method=payment_method,
        waiter_id=staff_id,
        people_for=body.get('people_for', 1) or 1,
        total=total,
        service_charge=service_charge,
    )
    order.save()
    from core.order_notify import notify_order_update
    notify_order_update(order)
    items = body.get('items', [])
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get('product_id') or None,
            product_variant_id=it.get('product_variant_id') or None,
            combo_set_id=it.get('combo_set_id') or None,
            price=Decimal(str(it.get('price', 0))),
            quantity=Decimal(str(it.get('quantity', 1))),
            total=Decimal(str(it.get('total', 0))),
        )
    return JsonResponse(_order_to_dict(order, include_items=True, request=request), status=201)


@require_http_methods(['GET'])
def waiter_order_payment_qr(request, pk):
    """GET /api/waiter/orders/<id>/payment-qr/ - returns PNG QR for Esewa payment (waiter's orders only)."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(Order.objects.select_related('restaurant'), pk=pk)
    if o.waiter_id != staff_id:
        return JsonResponse({'error': 'Forbidden', 'detail': 'Order not assigned to you'}, status=403)
    if o.payment_status in (PaymentStatus.PAID, PaymentStatus.SUCCESS):
        return JsonResponse({'error': 'Order already paid'}, status=400)
    amount_override = request.GET.get('amount')
    if amount_override is not None:
        try:
            amount_override = Decimal(amount_override)
        except Exception:
            amount_override = None
    png_bytes, err = generate_esewa_qr_png(o, amount_override=amount_override)
    if err:
        return JsonResponse({'error': err}, status=400)
    return HttpResponse(png_bytes, content_type='image/png')
