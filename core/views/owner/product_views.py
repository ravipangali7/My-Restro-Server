"""Owner product (menu item) list, detail, create, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import Product, ProductVariant, Category, Unit, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _product_to_dict(p, include_variants=False, request=None):
    image_url = None
    if p.image:
        image_url = p.image.url
        if request and image_url:
            image_url = request.build_absolute_uri(image_url)
    d = {
        'id': p.id,
        'name': p.name,
        'restaurant_id': p.restaurant_id,
        'restaurant_name': p.restaurant.name if getattr(p, 'restaurant', None) else None,
        'category_id': p.category_id,
        'category_name': p.category.name if getattr(p, 'category', None) else None,
        'image': image_url,
        'is_active': p.is_active,
        'is_available': p.is_active,
        'dish_type': p.dish_type,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
    }
    variants = list(p.variants.select_related('unit').all())
    if variants:
        primary = str(variants[0].price)
        d['primary_price'] = primary
        d['price'] = primary
        d['primary_unit_id'] = variants[0].unit_id
    else:
        d['price'] = None
    if include_variants:
        d['variants'] = [
            {
                'id': v.id,
                'unit_id': v.unit_id,
                'unit_name': v.unit.name if v.unit else None,
                'price': str(v.price),
                'discount_type': v.discount_type or '',
                'discount': str(v.discount),
            }
            for v in variants
        ]
    return d


def _product_qs(request):
    rid = get_restaurant_ids(request)
    qs = Product.objects.select_related('category').prefetch_related('variants__unit')
    if not getattr(request.user, 'is_superuser', False):
        if not rid:
            return qs.none()
        qs = qs.filter(restaurant_id__in=rid)
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_product_list(request):
    """List products (menu items) with primary price and stats."""
    qs = _product_qs(request)
    category_id = request.GET.get('category_id')
    if category_id:
        qs = qs.filter(category_id=category_id)
    results = [_product_to_dict(p, request=request) for p in qs.order_by('name')]
    total_products = len(results)
    product_ids = [p['id'] for p in results]
    products_with_discount = Product.objects.filter(
        id__in=product_ids
    ).filter(variants__discount__gt=0).distinct().count() if product_ids else 0
    stats = {
        'total_products': total_products,
        'products_with_discount': products_with_discount,
    }
    return JsonResponse({'stats': stats, 'results': results})


@auth_required
@require_http_methods(['GET'])
def owner_product_detail(request, pk):
    """Product detail with variants."""
    rid = get_restaurant_ids(request)
    if not getattr(request.user, 'is_superuser', False) and not rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    qs = Product.objects.prefetch_related('variants__unit')
    if not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(restaurant_id__in=rid)
    p = get_object_or_404(qs.select_related('category', 'restaurant'), pk=pk)
    return JsonResponse(_product_to_dict(p, include_variants=True, request=request))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_product_create(request):
    """Create product. JSON: restaurant_id, category_id, name, is_active?, dish_type?, variants?: [{ unit_id, price, discount_type?, discount? }]"""
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
    category_id = body.get('category_id')
    if not category_id:
        return JsonResponse({'error': 'category_id required'}, status=400)
    category = get_object_or_404(Category, pk=category_id, restaurant=restaurant)
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    p = Product(
        restaurant=restaurant,
        category=category,
        name=name,
        is_active=bool(body.get('is_active', True)),
        dish_type=body.get('dish_type', 'veg'),
    )
    p.save()
    for v in body.get('variants', []):
        unit_id = v.get('unit_id')
        if not unit_id:
            continue
        ProductVariant.objects.create(
            product=p,
            unit_id=unit_id,
            price=Decimal(str(v.get('price', 0))),
            discount_type=v.get('discount_type') or '',
            discount=Decimal(str(v.get('discount', 0))),
        )
    return JsonResponse(_product_to_dict(p, include_variants=True, request=request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_product_update(request, pk):
    """Update product."""
    p = get_object_or_404(Product, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and p.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        p.name = str(body['name']).strip() or p.name
    if 'category_id' in body:
        p.category_id = body['category_id']
    if 'is_active' in body:
        p.is_active = bool(body['is_active'])
    if 'dish_type' in body:
        p.dish_type = body['dish_type']
    p.save()
    return JsonResponse(_product_to_dict(p, include_variants=True, request=request))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_product_upload_image(request, pk):
    """POST multipart/form-data with 'image' file to set product image."""
    p = get_object_or_404(Product, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and p.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image') if request.FILES else None
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    p.image = image_file
    p.save()
    return JsonResponse(_product_to_dict(p, include_variants=True, request=request))


@auth_required
@require_http_methods(['DELETE'])
def owner_product_delete(request, pk):
    """Delete product."""
    p = get_object_or_404(Product, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and p.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    p.delete()
    return JsonResponse({'success': True}, status=200)
