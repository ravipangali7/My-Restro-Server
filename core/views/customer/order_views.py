"""Customer orders: list and detail for orders where customer is linked. Function-based."""
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db.models import Sum

from core.models import Order
from core.utils import customer_auth_required, get_customer_id_from_request
from core.invoice_utils import get_invoice_extras


def _order_to_dict(o, include_items=False):
    rest = getattr(o, 'restaurant', None)
    waiter = getattr(o, 'waiter', None)
    waiter_name = (waiter.user.get_full_name() or waiter.user.username) if waiter and getattr(waiter, 'user', None) else None
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
        'waiter_name': waiter_name,
        'customer_name': o.customer.name if getattr(o, 'customer', None) and o.customer else None,
        'people_for': o.people_for,
        'total': str(o.total),
        'service_charge': str(o.service_charge) if o.service_charge is not None else None,
        'discount': str(o.discount) if o.discount is not None else None,
        'reject_reason': o.reject_reason or '',
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'updated_at': o.updated_at.isoformat() if o.updated_at else None,
    }
    if include_items:
        d['items'] = []
        for sn, i in enumerate(o.items.select_related('product', 'combo_set').all(), start=1):
            item_name = 'Item'
            if i.combo_set_id and i.combo_set:
                item_name = i.combo_set.name or item_name
            elif i.product_id and i.product:
                item_name = i.product.name or item_name
            d['items'].append({
                'id': i.id,
                'sn': sn,
                'product_id': i.product_id,
                'item_name': item_name,
                'product_name': item_name,
                'price': str(i.price),
                'quantity': str(i.quantity),
                'total': str(i.total),
            })
    return d


@customer_auth_required
def customer_order_list(request):
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    qs = Order.objects.filter(customer_id=customer_id).select_related('restaurant', 'table').prefetch_related('items')
    total_revenue = qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
    stats = {
        'total': qs.count(),
        'pending': qs.filter(status='pending').count(),
        'running': qs.filter(status='running').count(),
        'ready': qs.filter(status='ready').count(),
        'rejected': qs.filter(status='rejected').count(),
        'paid': qs.filter(payment_status='paid').count(),
        'total_revenue': str(total_revenue),
    }
    results = [_order_to_dict(o) for o in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@customer_auth_required
def customer_order_detail(request, pk):
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(
        Order.objects.select_related('restaurant', 'table', 'waiter__user', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.customer_id != customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    d = _order_to_dict(o, include_items=True)
    d.update(get_invoice_extras(o))
    return JsonResponse(d)


@customer_auth_required
def customer_order_bill(request, pk):
    """GET /api/customer/orders/<id>/bill/?format=pdf - returns PDF bill for own order."""
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(
        Order.objects.select_related('table', 'restaurant', 'waiter__user', 'customer').prefetch_related('items__product', 'items__combo_set'),
        pk=pk,
    )
    if o.customer_id != customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.GET.get('format') != 'pdf':
        return JsonResponse({'error': 'Use ?format=pdf to download bill'}, status=400)
    from core.bill_pdf import order_bill_pdf_bytes
    pdf_bytes = order_bill_pdf_bytes(o, 'Order Bill')
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="order-{o.id}-bill.pdf"'
    return resp
