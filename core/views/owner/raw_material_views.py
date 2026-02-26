"""Owner raw material list, create, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from core.models import RawMaterial, Restaurant, Unit, Vendor
from core.utils import get_restaurant_ids, auth_required


def _raw_material_to_dict(r, low_stock=False):
    d = {
        'id': r.id,
        'name': r.name,
        'restaurant_id': r.restaurant_id,
        'vendor_id': r.vendor_id,
        'unit_id': r.unit_id,
        'unit_name': r.unit.name if r.unit else None,
        'price': str(r.price),
        'stock': str(r.stock),
        'min_stock': str(r.min_stock) if r.min_stock is not None else None,
        'image': r.image.url if getattr(r, 'image', None) and r.image else None,
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None,
    }
    if low_stock is not None:
        d['low_stock'] = low_stock
    return d


def _raw_material_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = RawMaterial.objects.all()
    elif rid:
        qs = RawMaterial.objects.filter(restaurant_id__in=rid)
    else:
        qs = RawMaterial.objects.none()
    return qs.select_related('unit', 'vendor')


@auth_required
@require_http_methods(['GET'])
def owner_raw_material_list(request):
    qs = _raw_material_qs(request)
    low_ids = set()
    for r in qs:
        if r.min_stock is not None and r.stock is not None and r.stock <= r.min_stock:
            low_ids.add(r.id)
    results = []
    for r in qs.order_by('name'):
        results.append(_raw_material_to_dict(r, low_stock=r.id in low_ids))
    total = len(results)
    low_count = len(low_ids)
    stats = {'total': total, 'low_stock': low_count, 'high_stock': total - low_count}
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_raw_material_create(request):
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
    unit_id = body.get('unit_id')
    if not unit_id:
        return JsonResponse({'error': 'unit_id required'}, status=400)
    unit = get_object_or_404(Unit, pk=unit_id, restaurant=restaurant)
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    r = RawMaterial(
        restaurant=restaurant,
        name=name,
        vendor_id=body.get('vendor_id') or None,
        unit=unit,
        price=Decimal(str(body.get('price', 0))),
        stock=Decimal(str(body.get('stock', 0))),
        min_stock=Decimal(str(body.get('min_stock', 0))) if body.get('min_stock') is not None else None,
    )
    r.save()
    return JsonResponse(_raw_material_to_dict(r), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_raw_material_update(request, pk):
    r = get_object_or_404(RawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        r.name = str(body['name']).strip() or r.name
    if 'vendor_id' in body:
        r.vendor_id = body['vendor_id'] or None
    if 'unit_id' in body:
        r.unit_id = body['unit_id']
    if 'price' in body:
        r.price = Decimal(str(body['price']))
    if 'stock' in body:
        r.stock = Decimal(str(body['stock']))
    if 'min_stock' in body:
        r.min_stock = Decimal(str(body['min_stock'])) if body['min_stock'] is not None else None
    r.save()
    return JsonResponse(_raw_material_to_dict(r))


@auth_required
@require_http_methods(['DELETE'])
def owner_raw_material_delete(request, pk):
    r = get_object_or_404(RawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    r.delete()
    return JsonResponse({'success': True}, status=200)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_raw_material_upload_image(request, pk):
    r = get_object_or_404(RawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    r.image = image_file
    r.save(update_fields=['image'])
    return JsonResponse(_raw_material_to_dict(r))
