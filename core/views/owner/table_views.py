"""Owner/Manager table list, create, update, delete. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import Table, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _table_to_dict(t):
    return {
        'id': t.id,
        'restaurant_id': t.restaurant_id,
        'name': t.name,
        'capacity': t.capacity,
        'floor': t.floor or '',
        'near_by': t.near_by or '',
        'notes': getattr(t, 'notes', '') or '',
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None,
    }


def _table_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Table.objects.all()
    elif rid:
        qs = Table.objects.filter(restaurant_id__in=rid)
    else:
        qs = Table.objects.none()
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_table_list(request):
    qs = _table_qs(request)
    floor = request.GET.get('floor')
    if floor:
        qs = qs.filter(floor=floor)
    results = [_table_to_dict(t) for t in qs.order_by('floor', 'name')]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_table_create(request):
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
    try:
        capacity = int(body.get('capacity', 0))
    except (TypeError, ValueError):
        capacity = 0
    if capacity < 0:
        return JsonResponse({'error': 'capacity must be >= 0'}, status=400)
    t = Table(
        restaurant=restaurant,
        name=name,
        capacity=capacity,
        floor=body.get('floor', ''),
        near_by=body.get('near_by', ''),
        notes=body.get('notes', '') or '',
    )
    t.save()
    return JsonResponse(_table_to_dict(t), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_table_update(request, pk):
    t = get_object_or_404(Table, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and t.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        new_name = str(body['name']).strip()
        if new_name:
            t.name = new_name
        else:
            return JsonResponse({'error': 'name cannot be empty'}, status=400)
    if 'capacity' in body:
        try:
            cap = int(body['capacity'])
        except (TypeError, ValueError):
            return JsonResponse({'error': 'capacity must be a number'}, status=400)
        if cap < 0:
            return JsonResponse({'error': 'capacity must be >= 0'}, status=400)
        t.capacity = cap
    if 'floor' in body:
        t.floor = str(body.get('floor', ''))
    if 'near_by' in body:
        t.near_by = str(body.get('near_by', ''))
    if 'notes' in body:
        t.notes = str(body.get('notes', '')) or ''
    t.save()
    return JsonResponse(_table_to_dict(t))


@auth_required
@require_http_methods(['DELETE'])
def owner_table_delete(request, pk):
    t = get_object_or_404(Table, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and t.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    t.delete()
    return JsonResponse({'success': True}, status=200)
