"""Owner stock logs list. Function-based."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import StockLog
from core.utils import get_restaurant_ids, auth_required


def _stock_log_to_dict(s):
    return {
        'id': s.id,
        'restaurant_id': s.restaurant_id,
        'raw_material_id': s.raw_material_id,
        'raw_material_name': s.raw_material.name if s.raw_material else None,
        'type': s.type,
        'quantity': str(s.quantity),
        'purchase_id': s.purchase_id,
        'order_id': s.order_id,
        'created_at': s.created_at.isoformat() if s.created_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def owner_stock_log_list(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'results': []})
    qs = StockLog.objects.filter(restaurant_id__in=rid).select_related('raw_material').order_by('-created_at')[:100]
    results = [_stock_log_to_dict(s) for s in qs]
    return JsonResponse({'results': results})
