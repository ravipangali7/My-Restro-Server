"""Kitchen order list and status update. Scoped to kitchen's restaurant(s). Only pending/accepted/running/ready."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from django.db.models import Q

from core.models import Order, OrderStatus
from core.utils import get_restaurant_ids, auth_required
from core.permissions import kitchen_required


def _kitchen_order_to_dict(o):
    """Serialize order for kitchen dashboard: id, table/delivery, items with image, notes, total, created_at, status."""
    table_display = o.table.name if o.table else (o.table_number or (o.address or '—'))
    items = []
    for i in o.items.select_related('product', 'combo_set').all():
        name = None
        product_image = None
        if i.combo_set_id and i.combo_set:
            name = i.combo_set.name
            if getattr(i.combo_set, 'image', None) and i.combo_set.image:
                product_image = i.combo_set.image.url
        elif i.product_id and i.product:
            name = i.product.name
            if getattr(i.product, 'image', None) and i.product.image:
                product_image = i.product.image.url
        items.append({
            'name': name or '—',
            'quantity': str(i.quantity),
            'total': str(i.total),
            'product_image': product_image,
        })
    return {
        'id': o.id,
        'table_or_delivery': table_display,
        'order_type': o.order_type or 'table',
        'address': o.address or '',
        'items': items,
        'special_notes': o.reject_reason or '',  # reuse field for display; empty when not rejected
        'total': str(o.total),
        'service_charge': str(o.service_charge) if o.service_charge is not None else None,
        'customer_name': o.customer.name if getattr(o, 'customer', None) and o.customer else None,
        'customer_phone': o.customer.phone if getattr(o, 'customer', None) and o.customer else None,
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'status': o.status,
    }


KITCHEN_ALLOWED_STATUSES = (OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.RUNNING, OrderStatus.READY)
KITCHEN_ALLOWED_NEXT = {
    OrderStatus.PENDING: [OrderStatus.ACCEPTED, OrderStatus.REJECTED],
    OrderStatus.ACCEPTED: [OrderStatus.RUNNING],
    OrderStatus.RUNNING: [OrderStatus.READY],
    OrderStatus.READY: [OrderStatus.SERVED],
}


@auth_required
@kitchen_required
@require_http_methods(['GET'])
def kitchen_orders(request):
    """List orders for kitchen: status in pending, accepted, running, ready. Scoped by restaurant."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'results': []})
    qs = (
        Order.objects.filter(restaurant_id__in=rid, status__in=KITCHEN_ALLOWED_STATUSES)
        .select_related('table', 'restaurant', 'customer')
        .prefetch_related('items__product', 'items__combo_set')
        .order_by('-created_at')
    )
    search = request.GET.get('search', '').strip()
    if search:
        search_q = Q()
        if search.isdigit():
            search_q |= Q(id=int(search))
        search_q |= Q(table_number__icontains=search) | Q(table__name__icontains=search)
        search_q |= Q(customer__name__icontains=search)
        qs = qs.filter(search_q)
    results = [_kitchen_order_to_dict(o) for o in qs[:200]]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@kitchen_required
@require_http_methods(['PUT', 'PATCH'])
def kitchen_order_update(request, pk):
    """Update order status. Allowed: accepted, running, ready, rejected (with reason), served. Scoped by restaurant."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(
        Order.objects.select_related('restaurant', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.restaurant_id not in rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'status' not in body:
        return JsonResponse(_kitchen_order_to_dict(o))
    new_status = body['status']
    allowed_next = KITCHEN_ALLOWED_NEXT.get(o.status, [])
    if new_status not in allowed_next:
        return JsonResponse(
            {'error': f'Invalid transition from {o.status} to {new_status}'},
            status=400,
        )
    if new_status == OrderStatus.REJECTED:
        reject_reason = (body.get('reject_reason') or '').strip()
        if not reject_reason:
            return JsonResponse({'error': 'Rejection reason is required'}, status=400)
        o.reject_reason = reject_reason
    o.status = new_status
    o.save()
    from core.order_notify import notify_order_update
    notify_order_update(o)
    if new_status in KITCHEN_ALLOWED_STATUSES:
        return JsonResponse(_kitchen_order_to_dict(o))
    return JsonResponse({'id': o.id, 'status': o.status})
