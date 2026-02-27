"""Waiter QR stand orders: list and create, scoped to waiter's restaurant."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum

from core.models import QrStandOrder, Restaurant
from core.permissions import get_waiter_restaurant


def _qr_order_to_dict(q):
    return {
        'id': q.id,
        'restaurant_id': q.restaurant_id,
        'restaurant_name': q.restaurant.name if q.restaurant else None,
        'quantity': q.quantity,
        'total': str(q.total),
        'status': q.status,
        'payment_status': q.payment_status,
        'created_at': q.created_at.isoformat() if q.created_at else None,
    }


@require_http_methods(['GET'])
def waiter_qr_order_list(request):
    """List QR stand orders for the waiter's restaurant."""
    restaurant = get_waiter_restaurant(request)
    if not restaurant:
        return JsonResponse({'error': 'No restaurant assigned'}, status=403)
    qs = QrStandOrder.objects.filter(restaurant=restaurant).select_related('restaurant')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    total_orders = qs.count()
    pending = qs.filter(status='pending').count()
    accepted = qs.filter(status='accepted').count()
    delivered = qs.filter(status='delivered').count()
    revenue = qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    stats = {
        'total_orders': total_orders,
        'pending': pending,
        'accepted': accepted,
        'delivered': delivered,
        'revenue': str(revenue),
    }
    results = [_qr_order_to_dict(q) for q in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@require_http_methods(['POST'])
def waiter_qr_order_create(request):
    """Create QR stand order for the waiter's restaurant only."""
    restaurant = get_waiter_restaurant(request)
    if not restaurant:
        return JsonResponse({'error': 'No restaurant assigned'}, status=403)
    if not getattr(restaurant, 'is_restaurant', True):
        return JsonResponse({'error': 'Restaurant is inactive'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    restaurant_id = body.get('restaurant_id')
    if restaurant_id is not None and int(restaurant_id) != restaurant.id:
        return JsonResponse({'error': 'Restaurant not allowed'}, status=403)
    quantity = int(body.get('quantity', 1))
    total = Decimal(str(body.get('total', 0)))
    q = QrStandOrder(
        restaurant=restaurant,
        quantity=quantity,
        total=total,
        status='pending',
        payment_status='pending',
    )
    q.save()
    return JsonResponse(_qr_order_to_dict(q), status=201)
