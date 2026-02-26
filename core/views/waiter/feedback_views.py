"""Waiter my feedback: list only where staff_id=current waiter. Function-based."""
from django.http import JsonResponse

from core.models import Feedback
from core.utils import get_waiter_staff_id


def _feedback_to_dict(f):
    return {
        'id': f.id,
        'restaurant_id': f.restaurant_id,
        'customer_id': f.customer_id,
        'customer_name': f.customer.name if f.customer else None,
        'order_id': f.order_id,
        'staff_id': f.staff_id,
        'rating': f.rating,
        'review': f.review or '',
        'created_at': f.created_at.isoformat() if f.created_at else None,
    }


def waiter_feedback_list(request):
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'stats': {}, 'results': []})
    qs = Feedback.objects.filter(staff_id=staff_id).select_related('customer', 'order')
    from django.db.models import Avg
    avg_rating = qs.aggregate(a=Avg('rating'))['a']
    stats = {'total': qs.count(), 'average_rating': float(avg_rating) if avg_rating is not None else 0}
    results = [_feedback_to_dict(f) for f in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})
