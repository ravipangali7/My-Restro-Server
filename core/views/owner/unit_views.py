"""Owner unit list, create, update, delete. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import Unit, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _unit_to_dict(u):
    return {
        'id': u.id,
        'name': u.name,
        'symbol': u.symbol or '',
        'restaurant_id': u.restaurant_id,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'updated_at': u.updated_at.isoformat() if u.updated_at else None,
    }


def _unit_qs(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return Unit.objects.none()
    qs = Unit.objects.all()
    if rid and not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(restaurant_id__in=rid)
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_unit_list(request):
    qs = _unit_qs(request)
    results = [_unit_to_dict(u) for u in qs.order_by('name')]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_unit_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    restaurant_id = body.get('restaurant_id')
    if not restaurant_id:
        return JsonResponse({'error': 'restaurant_id required'}, status=400)
    if rid and int(restaurant_id) not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    u = Unit(restaurant=restaurant, name=name, symbol=body.get('symbol', ''))
    u.save()
    return JsonResponse(_unit_to_dict(u), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_unit_update(request, pk):
    u = get_object_or_404(Unit, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and u.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        u.name = str(body['name']).strip() or u.name
    if 'symbol' in body:
        u.symbol = str(body.get('symbol', ''))
    u.save()
    return JsonResponse(_unit_to_dict(u))


@auth_required
@require_http_methods(['DELETE'])
def owner_unit_delete(request, pk):
    u = get_object_or_404(Unit, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and u.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    u.delete()
    return JsonResponse({'success': True}, status=200)
