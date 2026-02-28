"""Owner purchase list, detail, create, update. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum

from core.models import Purchase, PurchaseItem, Restaurant, RawMaterial
from core.utils import get_restaurant_ids, auth_required, paginate_queryset, parse_date


def _purchase_to_dict(p, include_items=False):
    d = {
        'id': p.id,
        'restaurant_id': p.restaurant_id,
        'subtotal': str(p.subtotal),
        'discount_type': p.discount_type or '',
        'discount': str(p.discount),
        'total': str(p.total),
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
    }
    if include_items:
        d['items'] = [
            {
                'id': i.id,
                'raw_material_id': i.raw_material_id,
                'raw_material_name': i.raw_material.name if i.raw_material else None,
                'raw_material_image': i.raw_material.image.url if i.raw_material and getattr(i.raw_material, 'image', None) and i.raw_material.image else None,
                'price': str(i.price),
                'quantity': str(i.quantity),
                'total': str(i.total),
            }
            for i in p.items.select_related('raw_material').all()
        ]
    return d


def _purchase_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Purchase.objects.all()
    elif rid:
        qs = Purchase.objects.filter(restaurant_id__in=rid)
    else:
        qs = Purchase.objects.none()
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_purchase_list(request):
    qs = _purchase_qs(request)
    start_date = parse_date(request.GET.get('start_date') or request.GET.get('date_from'))
    end_date = parse_date(request.GET.get('end_date') or request.GET.get('date_to'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    search = (request.GET.get('search') or '').strip()
    if search:
        try:
            sid = int(search)
            qs = qs.filter(id=sid)
        except ValueError:
            pass
    agg = qs.aggregate(total_sum=Sum('total'))
    stats = {'total_purchases': qs.count(), 'total_amount': str(agg['total_sum'] or 0)}
    qs_paged, pagination = paginate_queryset(qs.order_by('-created_at'), request, default_page_size=20)
    results = [_purchase_to_dict(p) for p in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@auth_required
@require_http_methods(['GET'])
def owner_purchase_detail(request, pk):
    rid = get_restaurant_ids(request)
    if not getattr(request.user, 'is_superuser', False) and not rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    qs = Purchase.objects.prefetch_related('items__raw_material')
    if not getattr(request.user, 'is_superuser', False):
        qs = qs.filter(restaurant_id__in=rid)
    p = get_object_or_404(qs, pk=pk)
    return JsonResponse(_purchase_to_dict(p, include_items=True))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_purchase_create(request):
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
    subtotal = Decimal('0')
    items_data = body.get('items', [])
    for it in items_data:
        price = Decimal(str(it.get('price', 0)))
        qty = Decimal(str(it.get('quantity', 0)))
        subtotal += price * qty
    p = Purchase(
        restaurant=restaurant,
        subtotal=subtotal,
        discount_type=body.get('discount_type', ''),
        discount=Decimal(str(body.get('discount', 0))),
    )
    p.save()
    for it in items_data:
        raw_material_id = it.get('raw_material_id')
        if not raw_material_id:
            continue
        rm = get_object_or_404(RawMaterial, pk=raw_material_id, restaurant=restaurant)
        price = Decimal(str(it.get('price', 0)))
        qty = Decimal(str(it.get('quantity', 0)))
        total = price * qty
        PurchaseItem.objects.create(
            purchase=p, raw_material=rm, price=price, quantity=qty, total=total
        )
    p.refresh_from_db()
    return JsonResponse(_purchase_to_dict(p, include_items=True), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_purchase_update(request, pk):
    p = get_object_or_404(Purchase, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and p.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'subtotal' in body:
        p.subtotal = Decimal(str(body['subtotal']))
    if 'discount_type' in body:
        p.discount_type = body.get('discount_type', '')
    if 'discount' in body:
        p.discount = Decimal(str(body['discount']))
    p.save()
    return JsonResponse(_purchase_to_dict(p, include_items=True))
