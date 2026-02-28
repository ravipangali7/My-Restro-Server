"""Owner order list, detail, create, update. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q

from core.models import Order, OrderItem, Restaurant, OrderStatus, OrderType, PaymentStatus, Customer
from core.utils import get_restaurant_ids, auth_required, paginate_queryset, parse_date
from core.constants import ALLOWED_COUNTRY_CODES, normalize_country_code
from core.invoice_utils import get_invoice_extras


def _order_to_dict(o, include_items=False):
    d = {
        'id': o.id,
        'customer_id': o.customer_id,
        'restaurant_id': o.restaurant_id,
        'restaurant_name': o.restaurant.name if getattr(o, 'restaurant', None) else None,
        'restaurant_address': getattr(o.restaurant, 'address', None) or '' if getattr(o, 'restaurant', None) else '',
        'restaurant_phone': getattr(o.restaurant, 'phone', None) or '' if getattr(o, 'restaurant', None) else '',
        'table_id': o.table_id,
        'table_name': o.table.name if o.table else None,
        'table_number': o.table_number or '',
        'order_type': o.order_type,
        'address': o.address or '',
        'status': o.status,
        'payment_status': o.payment_status,
        'payment_method': o.payment_method or '',
        'waiter_id': o.waiter_id,
        'waiter_name': o.waiter.user.name if o.waiter and getattr(o.waiter, 'user', None) else None,
        'people_for': o.people_for,
        'total': str(o.total),
        'service_charge': str(o.service_charge) if o.service_charge is not None else None,
        'discount': str(o.discount) if o.discount is not None else None,
        'transaction_reference': o.transaction_reference or '',
        'reject_reason': o.reject_reason or '',
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'updated_at': o.updated_at.isoformat() if o.updated_at else None,
        'customer_name': o.customer.name if o.customer else None,
        'customer_phone': o.customer.phone if o.customer else None,
        'items_count': o.items.count(),
    }
    if include_items:
        d['items'] = []
        for i in o.items.select_related('product', 'product_variant', 'combo_set').all():
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
            elif i.product_id and i.product:
                item_dict['product_name'] = i.product.name
                if getattr(i.product, 'image', None) and i.product.image:
                    item_dict['product_image'] = i.product.image.url
            d['items'].append(item_dict)
    return d


def _order_qs(request):
    rid = get_restaurant_ids(request)
    qs = Order.objects.select_related('table', 'customer', 'waiter__user').prefetch_related('items')
    if rid and not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(restaurant_id__in=rid)
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_order_list(request):
    """List orders with optional date/search/pagination. Returns stats + results + pagination."""
    qs = _order_qs(request)
    # Date filters: support start_date/end_date and date_from/date_to
    start_date = parse_date(request.GET.get('start_date') or request.GET.get('date_from'))
    end_date = parse_date(request.GET.get('end_date') or request.GET.get('date_to'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    status = request.GET.get('status')
    if status and status != 'all':
        qs = qs.filter(status=status)
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(table__name__icontains=search)
            | Q(table_number__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(customer__phone__icontains=search)
        )
    total_revenue = qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    stats = {
        'total_orders': qs.count(),
        'pending': qs.filter(status=OrderStatus.PENDING).count(),
        'accepted': qs.filter(status=OrderStatus.ACCEPTED).count(),
        'running': qs.filter(status=OrderStatus.RUNNING).count(),
        'ready': qs.filter(status=OrderStatus.READY).count(),
        'rejected': qs.filter(status=OrderStatus.REJECTED).count(),
        'paid': qs.filter(payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]).count(),
        'total_revenue': str(total_revenue),
    }
    qs_paged, pagination = paginate_queryset(qs.order_by('-created_at'), request, default_page_size=20)
    results = [_order_to_dict(o) for o in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@auth_required
@require_http_methods(['GET'])
def owner_customer_order_list(request, pk):
    """All orders for a customer with items and product images. For customer detail / customer view."""
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse(
            {'error': 'Forbidden', 'detail': 'No restaurant access', 'locked': False},
            status=403,
        )
    restaurant_ids = list(rid) if rid else []
    if getattr(request.user, 'is_superuser', False):
        from core.models import Restaurant
        restaurant_ids = list(Restaurant.objects.values_list('id', flat=True))
    qs = Order.objects.filter(
        customer_id=pk,
        restaurant_id__in=restaurant_ids,
    ).select_related('table', 'customer', 'waiter__user').prefetch_related(
        'items__product', 'items__product_variant', 'items__combo_set'
    ).order_by('-created_at')[:100]
    results = [_order_to_dict(o, include_items=True) for o in qs]
    return JsonResponse({'results': results})


@auth_required
@require_http_methods(['GET'])
def owner_order_detail(request, pk):
    """Order detail with items."""
    rid = get_restaurant_ids(request)
    if not getattr(request.user, 'is_superuser', False) and not rid:
        return JsonResponse(
            {'error': 'Forbidden', 'detail': 'No restaurant access', 'locked': False},
            status=403,
        )
    qs = Order.objects.select_related('table', 'customer', 'waiter__user', 'restaurant').prefetch_related('items__product', 'items__combo_set')
    if not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(restaurant_id__in=rid)
    o = get_object_or_404(qs, pk=pk)
    d = _order_to_dict(o, include_items=True)
    d.update(get_invoice_extras(o))
    for i, it in enumerate(d.get('items', []), 1):
        it['sn'] = i
        it.setdefault('item_name', it.get('product_name'))
    return JsonResponse(d)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_order_create(request):
    """Create order. Required: restaurant_id, customer_name, country_code, customer_phone, payment_method. Optional: table_id, order_type, service_charge, items."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    restaurant_id = body.get('restaurant_id')
    if not restaurant_id:
        return JsonResponse({'error': 'restaurant_id required'}, status=400)
    if rid and int(restaurant_id) not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse(
            {'error': 'Forbidden', 'detail': 'Restaurant not in your scope', 'locked': False},
            status=403,
        )
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    if not getattr(restaurant, 'is_restaurant', True):
        return JsonResponse({'error': 'Restaurant is inactive'}, status=403)

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
    discount_raw = body.get('discount')
    discount_val = Decimal(str(discount_raw)) if discount_raw not in (None, '') else None

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
        waiter_id=body.get('waiter_id') or None,
        people_for=body.get('people_for', 1) or 1,
        total=total,
        service_charge=service_charge,
        discount=discount_val,
    )
    order.save()
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
    return JsonResponse(_order_to_dict(order, include_items=True), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_order_update(request, pk):
    """Update order status, payment_status, etc."""
    o = get_object_or_404(Order, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and o.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse(
            {'error': 'Forbidden', 'detail': 'Order restaurant not in your scope', 'locked': False},
            status=403,
        )
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'status' in body:
        o.status = body['status']
    if 'payment_status' in body:
        o.payment_status = body['payment_status']
    if 'payment_method' in body:
        o.payment_method = body['payment_method'] or ''
    if 'total' in body:
        try:
            o.total = Decimal(str(body['total']))
        except Exception:
            pass
    if 'table_number' in body:
        o.table_number = (body.get('table_number') or '').strip() or None
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
    return JsonResponse(_order_to_dict(o, include_items=True))


@auth_required
@require_http_methods(['GET'])
def owner_order_payment_qr(request, pk):
    """GET /api/owner/orders/<id>/payment-qr/ - returns PNG QR for Esewa payment."""
    o = get_object_or_404(Order.objects.select_related('restaurant'), pk=pk)
    rid = get_restaurant_ids(request)
    if rid and o.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden', 'detail': 'Order not in your scope'}, status=403)
    if o.payment_status in (PaymentStatus.PAID, PaymentStatus.SUCCESS):
        return JsonResponse({'error': 'Order already paid'}, status=400)
    from core.payment_qr import generate_esewa_qr_png
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


@auth_required
@require_http_methods(['GET'])
def owner_order_bill(request, pk):
    """GET /api/owner/orders/<id>/bill/?format=pdf - returns PDF bill. HTML optional."""
    o = get_object_or_404(
        Order.objects.select_related('table', 'restaurant', 'waiter__user', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    rid = get_restaurant_ids(request)
    if rid and o.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden', 'detail': 'Order not in your scope'}, status=403)
    if request.GET.get('format') == 'pdf':
        from core.bill_pdf import order_bill_pdf_bytes
        pdf_bytes = order_bill_pdf_bytes(o, 'Order Bill')
        resp = HttpResponse(pdf_bytes, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-bill.pdf"'
        return resp
    return JsonResponse({'error': 'Use ?format=pdf to download bill'}, status=400)
