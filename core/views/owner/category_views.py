"""Owner category list, create, update, delete. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Count

from core.models import Category, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _category_to_dict(c, item_count=None, request=None):
    image_url = c.image.url if c.image else None
    if image_url and request:
        image_url = request.build_absolute_uri(image_url)
    d = {
        'id': c.id,
        'name': c.name,
        'restaurant_id': c.restaurant_id,
        'image': image_url,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'updated_at': c.updated_at.isoformat() if c.updated_at else None,
    }
    if item_count is not None:
        d['item_count'] = item_count
    return d


def _category_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Category.objects.all()
    elif rid:
        qs = Category.objects.filter(restaurant_id__in=rid)
    else:
        qs = Category.objects.none()
    return qs.annotate(item_count=Count('products'))


@auth_required
@require_http_methods(['GET'])
def owner_category_list(request):
    qs = _category_qs(request)
    results = [_category_to_dict(c, item_count=c.item_count, request=request) for c in qs.order_by('name')]
    return JsonResponse({'results': results, 'total': len(results)})


def _parse_category_body(request):
    """Return (body dict, image file or None). Supports JSON or multipart/form-data."""
    image_file = request.FILES.get('image') if request.FILES else None
    if request.content_type and 'multipart/form-data' in request.content_type and request.POST:
        body = dict(request.POST)
        # Unwrap single-value lists from POST
        data = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in body.items()}
        if data.get('restaurant_id'):
            data['restaurant_id'] = int(data['restaurant_id']) if data['restaurant_id'] else None
        return data, image_file
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return {}, None
    return body, image_file


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_category_create(request):
    body, image_file = _parse_category_body(request)
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
    c = Category(restaurant=restaurant, name=name)
    if image_file:
        c.image = image_file
    c.save()
    return JsonResponse(_category_to_dict(c, request=request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_category_update(request, pk):
    c = get_object_or_404(Category, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if body.get('name') is not None:
        c.name = str(body['name']).strip() or c.name
    c.save()
    return JsonResponse(_category_to_dict(c, request=request))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_category_upload_image(request, pk):
    """POST multipart/form-data with 'image' file to set category image."""
    c = get_object_or_404(Category, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image') if request.FILES else None
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    c.image = image_file
    c.save()
    return JsonResponse(_category_to_dict(c, request=request))


@auth_required
@require_http_methods(['DELETE'])
def owner_category_delete(request, pk):
    c = get_object_or_404(Category, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and c.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    c.delete()
    return JsonResponse({'success': True}, status=200)
