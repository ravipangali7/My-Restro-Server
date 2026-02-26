"""Owner recipe mapping (ProductRawMaterial) list, create, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import ProductRawMaterial, Restaurant, Product, ProductVariant, RawMaterial
from core.utils import get_restaurant_ids, auth_required


def _recipe_to_dict(r):
    d = {
        'id': r.id,
        'restaurant_id': r.restaurant_id,
        'product_id': r.product_id,
        'product_name': r.product.name if r.product else None,
        'product_variant_id': r.product_variant_id,
        'raw_material_id': r.raw_material_id,
        'raw_material_name': r.raw_material.name if r.raw_material else None,
        'raw_material_quantity': str(r.raw_material_quantity),
        'unit_name': r.raw_material.unit.name if r.raw_material and getattr(r.raw_material, 'unit', None) else None,
        'created_at': r.created_at.isoformat() if r.created_at else None,
        'updated_at': r.updated_at.isoformat() if r.updated_at else None,
    }
    if getattr(r, 'image', None) and r.image:
        d['image'] = r.image.url
    return d


def _recipe_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = ProductRawMaterial.objects.all()
    elif rid:
        qs = ProductRawMaterial.objects.filter(restaurant_id__in=rid)
    else:
        qs = ProductRawMaterial.objects.none()
    return qs.select_related('product', 'product_variant', 'raw_material', 'raw_material__unit')


@auth_required
@require_http_methods(['GET'])
def owner_recipe_list(request):
    qs = _recipe_qs(request)
    results = [_recipe_to_dict(r) for r in qs.order_by('product__name', 'raw_material__name')]
    stats = {
        'total_mappings': len(results),
        'total_products': len(set(r['product_id'] for r in results)),
    }
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_recipe_create(request):
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
    product_id = body.get('product_id')
    raw_material_id = body.get('raw_material_id')
    if not product_id or not raw_material_id:
        return JsonResponse({'error': 'product_id and raw_material_id required'}, status=400)
    product = get_object_or_404(Product, pk=product_id, restaurant=restaurant)
    raw_material = get_object_or_404(RawMaterial, pk=raw_material_id, restaurant=restaurant)
    qty = Decimal(str(body.get('raw_material_quantity', 1)))
    r = ProductRawMaterial(
        restaurant=restaurant,
        product=product,
        product_variant_id=body.get('product_variant_id') or None,
        raw_material=raw_material,
        raw_material_quantity=qty,
    )
    r.save()
    return JsonResponse(_recipe_to_dict(r), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_recipe_update(request, pk):
    r = get_object_or_404(ProductRawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'product_variant_id' in body:
        r.product_variant_id = body['product_variant_id'] or None
    if 'raw_material_quantity' in body:
        r.raw_material_quantity = Decimal(str(body['raw_material_quantity']))
    r.save()
    return JsonResponse(_recipe_to_dict(r))


@auth_required
@require_http_methods(['DELETE'])
def owner_recipe_delete(request, pk):
    r = get_object_or_404(ProductRawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    r.delete()
    return JsonResponse({'success': True}, status=200)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_recipe_upload_image(request, pk):
    r = get_object_or_404(ProductRawMaterial, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and r.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    r.image = image_file
    r.save(update_fields=['image'])
    return JsonResponse(_recipe_to_dict(r))
