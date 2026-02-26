"""Owner feedback list. Function-based."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import Feedback
from core.utils import get_restaurant_ids, auth_required


def _feedback_to_dict(f):
    return {
        'id': f.id,
        'restaurant_id': f.restaurant_id,
        'customer_id': f.customer_id,
        'customer_name': f.customer.name if f.customer else None,
        'order_id': f.order_id,
        'staff_id': f.staff_id,
        'staff_name': f.staff.user.name if f.staff and getattr(f.staff, 'user', None) else None,
        'rating': f.rating,
        'review': f.review or '',
        'created_at': f.created_at.isoformat() if f.created_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def owner_feedback_list(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'results': []})
    qs = Feedback.objects.filter(restaurant_id__in=rid).select_related('customer', 'staff__user', 'order')
    results = [_feedback_to_dict(f) for f in qs.order_by('-created_at')[:100]]
    return JsonResponse({'results': results})
