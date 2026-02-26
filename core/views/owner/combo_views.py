"""Owner combo set list, create, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import ComboSet, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _combo_to_dict(c, request=None):
    product_ids = list(c.products.values_list('id', flat=True))
    product_names = list(c.products.values_list('name', flat=True))
    image_url = c.image.url if c.image else None
    if image_url and request:
        image_url = request.build_absolute_uri(image_url)
    return {
        'id': c.id,
        'name': c.name,
        'description': getattr(c, 'description', '') or '',
        'image': image_url,
        'restaurant_id': c.restaurant_id,
        'price': str(c.price),
        'product_ids': product_ids,
        'product_names': product_names,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'updated_at': c.updated_at.isoformat() if c.updated_at else None,
    }


def _combo_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = ComboSet.objects.all()
    elif rid:
        qs = ComboSet.objects.filter(restaurant_id__in=rid)
    else:
        qs = ComboSet.objects.none()
    return qs.prefetch_related('products')


@auth_required
@require_http_methods(['GET'])
def owner_combo_list(request):
    qs = _combo_qs(request)
    results = [_combo_to_dict(c, request=request) for c in qs.order_by('name')]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_combo_create(request):
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
        price = Decimal(str(body.get('price', 0)))
    except Exception:
        price = Decimal('0')
    description = (body.get('description') or '').strip()
    c = ComboSet(restaurant=restaurant, name=name, description=description, price=price)
    c.save()
    product_ids = body.get('product_ids', [])
    if product_ids:
        c.products.set(product_ids)
    return JsonResponse(_combo_to_dict(c, request=request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_combo_update(request, pk):
    c = get_object_or_404(ComboSet.objects.prefetch_related('products'), pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        c.name = str(body['name']).strip() or c.name
    if 'description' in body:
        c.description = (body.get('description') or '').strip()
    if 'price' in body:
        try:
            c.price = Decimal(str(body['price']))
        except Exception:
            pass
    if 'product_ids' in body:
        c.products.set(body['product_ids'] or [])
    c.save()
    return JsonResponse(_combo_to_dict(c, request=request))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_combo_upload_image(request, pk):
    """POST multipart/form-data with 'image' file to set combo set image."""
    c = get_object_or_404(ComboSet, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image') if request.FILES else None
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    c.image = image_file
    c.save()
    return JsonResponse(_combo_to_dict(c, request=request))


@auth_required
@require_http_methods(['DELETE'])
def owner_combo_delete(request, pk):
    c = get_object_or_404(ComboSet, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    c.delete()
    return JsonResponse({'success': True}, status=200)
