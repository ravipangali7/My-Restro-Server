"""Function-based views for customer dashboard."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Avg

from core.models import Order, Feedback
from core.utils import customer_auth_required, get_customer_id_from_request


@require_http_methods(['GET'])
@customer_auth_required
def customer_dashboard(request):
    """Customer dashboard: stats and lists using model-aligned keys."""
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    order_qs = Order.objects.filter(customer_id=customer_id)
    total_orders = order_qs.count()
    total_spent = order_qs.exclude(status='rejected').aggregate(s=Sum('total'))['s'] or Decimal('0')
    avg_order = str(total_spent / total_orders) if total_orders else '0'
    feedback_qs = Feedback.objects.filter(customer_id=customer_id)
    avg_rating = feedback_qs.aggregate(a=Avg('rating'))['a']
    avg_rating_str = f'{float(avg_rating):.1f}' if avg_rating is not None else '0'
    recent_orders = [
        {'id': str(o.id), 'total': str(o.total), 'status': o.status, 'items': [], 'created_at': o.created_at.isoformat() if o.created_at else None}
        for o in order_qs.order_by('-created_at')[:10]
    ]
    reviews = [
        {'id': f.id, 'rating': f.rating, 'review': f.review or '', 'created_at': f.created_at.isoformat() if f.created_at else None}
        for f in feedback_qs.order_by('-created_at')[:10]
    ]
    data = {
        'total_orders': total_orders,
        'total_spent': str(total_spent),
        'avg_order': avg_order,
        'avg_rating': avg_rating_str,
        'loyalty_points': 0,
        'loyalty_tier': 'Bronze',
        'monthly_spending': [],
        'favorite_categories': [],
        'order_frequency': [],
        'favorite_items': [],
        'recent_orders': recent_orders,
        'reviews': reviews,
    }
    return JsonResponse(data)
