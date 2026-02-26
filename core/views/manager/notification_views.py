"""Manager bulk notifications list, create. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import BulkNotification, Restaurant
from core.utils import get_restaurant_ids, auth_required
from core import services


def _notification_to_dict(n):
    return {
        'id': n.id,
        'restaurant_id': n.restaurant_id,
        'type': n.type,
        'message': n.message,
        'sent_count': n.sent_count,
        'total_count': n.total_count,
        'image': n.image.url if n.image else None,
        'created_at': n.created_at.isoformat() if n.created_at else None,
    }


@require_http_methods(['GET'])
def manager_notification_list(request):
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'results': []})
    qs = BulkNotification.objects.filter(restaurant_id__in=rid).order_by('-created_at')[:100]
    results = [_notification_to_dict(n) for n in qs]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def manager_notification_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    restaurant_id = body.get('restaurant_id')
    if not restaurant_id:
        return JsonResponse({'error': 'restaurant_id required'}, status=400)
    if int(restaurant_id) not in rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    message = (body.get('message') or '').strip()
    if not message:
        return JsonResponse({'error': 'message required'}, status=400)
    n = BulkNotification(
        restaurant=restaurant,
        type=body.get('type', 'sms'),
        message=message,
    )
    n.save()
    customer_ids = body.get('customer_ids', [])
    if customer_ids:
        n.customers.set(customer_ids)
    n.total_count = n.customers.count()
    n.save()
    if n.type == 'whatsapp':
        services.record_whatsapp_usage(restaurant)
    return JsonResponse(_notification_to_dict(n), status=201)
