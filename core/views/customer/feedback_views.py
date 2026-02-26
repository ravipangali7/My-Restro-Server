"""Customer my feedback: list only where customer_id=current customer. Function-based."""
from django.http import JsonResponse
from django.db.models import Avg

from core.models import Feedback
from core.utils import customer_auth_required, get_customer_id_from_request


def _feedback_to_dict(f):
    return {
        'id': f.id,
        'restaurant_id': f.restaurant_id,
        'restaurant_name': f.restaurant.name if f.restaurant else None,
        'customer_id': f.customer_id,
        'order_id': f.order_id,
        'staff_id': f.staff_id,
        'rating': f.rating,
        'review': f.review or '',
        'created_at': f.created_at.isoformat() if f.created_at else None,
    }


@customer_auth_required
def customer_feedback_list(request):
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    qs = Feedback.objects.filter(customer_id=customer_id).select_related('restaurant', 'order')
    avg_rating = qs.aggregate(a=Avg('rating'))['a']
    stats = {'total': qs.count(), 'average_rating': float(avg_rating) if avg_rating is not None else 0}
    results = [_feedback_to_dict(f) for f in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})
