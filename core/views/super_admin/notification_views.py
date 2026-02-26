"""Super Admin notifications list (BulkNotification across all restaurants). Function-based."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import BulkNotification, Restaurant


def _notification_to_dict(n):
    return {
        'id': n.id,
        'restaurant_id': n.restaurant_id,
        'restaurant_name': n.restaurant.name if n.restaurant_id else None,
        'type': n.type,
        'message': n.message[:200] if n.message else '',
        'sent_count': n.sent_count,
        'total_count': n.total_count,
        'image': n.image.url if n.image else None,
        'created_at': n.created_at.isoformat() if n.created_at else None,
    }


@require_http_methods(['GET'])
def super_admin_notification_list(request):
    """List all bulk notifications across restaurants."""
    qs = BulkNotification.objects.all().select_related('restaurant').order_by('-created_at')[:100]
    results = [_notification_to_dict(n) for n in qs]
    total = BulkNotification.objects.count()
    stats = {'total': total}
    return JsonResponse({'stats': stats, 'results': results})
