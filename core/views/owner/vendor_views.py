"""Owner vendor list, create, update, delete, analytics. Function-based."""
import json
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from django.utils import timezone

from core.models import Vendor, Restaurant, PurchaseItem, PaidRecord
from core.utils import get_restaurant_ids, auth_required
from core.constants import ALLOWED_COUNTRY_CODES


def _vendor_to_dict(v, to_pay=None, to_receive=None):
    d = {
        'id': v.id,
        'name': v.name,
        'role': getattr(v, 'role', '') or '',
        'phone': v.phone or '',
        'country_code': getattr(v, 'country_code', '') or '',
        'restaurant_id': v.restaurant_id,
        'image': v.image.url if v.image else None,
        'created_at': v.created_at.isoformat() if v.created_at else None,
        'updated_at': v.updated_at.isoformat() if v.updated_at else None,
    }
    if to_pay is not None:
        d['to_pay'] = str(to_pay)
    if to_receive is not None:
        d['to_receive'] = str(to_receive)
    if to_pay is None and hasattr(v, 'to_pay'):
        d['to_pay'] = str(v.to_pay)
    if to_receive is None and hasattr(v, 'to_receive'):
        d['to_receive'] = str(v.to_receive)
    return d


def _vendor_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Vendor.objects.all()
    elif rid:
        qs = Vendor.objects.filter(restaurant_id__in=rid)
    else:
        qs = Vendor.objects.none()
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_vendor_list(request):
    qs = _vendor_qs(request)
    results = [_vendor_to_dict(v) for v in qs.order_by('name')]
    agg = qs.aggregate(to_pay=Sum('to_pay'), to_receive=Sum('to_receive'))
    stats = {
        'total': qs.count(),
        'total_to_pay': str(agg['to_pay'] or 0),
        'total_to_receive': str(agg['to_receive'] or 0),
    }
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_vendor_create(request):
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
    phone = (body.get('phone') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    country_code = (body.get('country_code') or '').strip()
    if country_code and country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({'error': 'Invalid country_code'}, status=400)
    v = Vendor(
        restaurant=restaurant,
        name=name,
        role=body.get('role', '') or '',
        phone=phone,
        country_code=country_code,
    )
    v.save()
    return JsonResponse(_vendor_to_dict(v), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_vendor_update(request, pk):
    v = get_object_or_404(Vendor, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and v.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        v.name = str(body['name']).strip() or v.name
    if 'role' in body:
        v.role = str(body.get('role', '')) or ''
    if 'phone' in body:
        v.phone = str(body.get('phone', '')) or ''
    if 'country_code' in body:
        v.country_code = str(body.get('country_code', '')) or ''
    v.save()
    return JsonResponse(_vendor_to_dict(v))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_vendor_upload_image(request, pk):
    """Upload vendor image. Multipart form with 'image' file."""
    v = get_object_or_404(Vendor, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and v.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    v.image = image_file
    v.save()
    return JsonResponse(_vendor_to_dict(v))


@auth_required
@require_http_methods(['DELETE'])
def owner_vendor_delete(request, pk):
    v = get_object_or_404(Vendor, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and v.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    v.delete()
    return JsonResponse({'success': True}, status=200)


@auth_required
@require_http_methods(['GET'])
def owner_vendor_analytics(request, pk):
    """Deep-relation analytics for a single vendor: stats, supply trend, material-wise, paid/due, payment history, supply transactions."""
    v = get_object_or_404(Vendor, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and v.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    # Base queryset: purchase items where raw_material belongs to this vendor
    items_qs = PurchaseItem.objects.filter(raw_material__vendor_id=v.id).select_related(
        'raw_material', 'raw_material__unit', 'purchase', 'purchase__restaurant'
    )

    # Stats
    supply_agg = items_qs.aggregate(
        total_supplies=Count('id'),
        total_amount=Sum('total'),
    )
    stats = {
        'total_supplies': supply_agg['total_supplies'] or 0,
        'total_amount': str(supply_agg['total_amount'] or 0),
        'pending_due': str(v.to_pay),
    }

    # Restaurant supplied (single in current schema)
    restaurant_supplied = {
        'id': v.restaurant_id,
        'name': v.restaurant.name if v.restaurant else None,
    }

    # Supply trend (last 90 days): by date
    since = timezone.now().date() - timedelta(days=90)
    trend_agg = (
        PurchaseItem.objects.filter(raw_material__vendor_id=v.id, purchase__created_at__date__gte=since)
        .values('purchase__created_at__date')
        .annotate(total_amount=Sum('total'), supply_count=Count('id'))
        .order_by('purchase__created_at__date')
    )
    supply_trend = [
        {
            'date': row['purchase__created_at__date'].isoformat() if row['purchase__created_at__date'] else None,
            'total_amount': str(row['total_amount'] or 0),
            'supply_count': row['supply_count'],
        }
        for row in trend_agg
    ]

    # Material-wise supply
    material_agg = (
        PurchaseItem.objects.filter(raw_material__vendor_id=v.id)
        .values('raw_material__name')
        .annotate(total_quantity=Sum('quantity'), total_value=Sum('total'))
    )
    material_wise_supply = [
        {
            'raw_material_name': row['raw_material__name'] or '—',
            'total_quantity': str(row['total_quantity'] or 0),
            'total_value': str(row['total_value'] or 0),
        }
        for row in material_agg
    ]

    # Paid vs Due
    paid_agg = PaidRecord.objects.filter(vendor_id=v.id).aggregate(s=Sum('amount'))
    paid_total = str(paid_agg['s'] or 0)
    due_total = str(v.to_pay)

    # Payment history
    paid_records = PaidRecord.objects.filter(vendor_id=v.id).order_by('-created_at')[:100]
    payment_history = [
        {
            'id': pr.id,
            'amount': str(pr.amount),
            'payment_method': pr.payment_method or '',
            'remarks': pr.remarks or '',
            'created_at': pr.created_at.isoformat() if pr.created_at else None,
        }
        for pr in paid_records
    ]

    # Supply transactions table
    supply_transactions = []
    for item in items_qs.order_by('-purchase__created_at')[:200]:
        purchase = item.purchase
        raw = item.raw_material
        supply_transactions.append({
            'purchase_id': purchase.id if purchase else None,
            'purchase_date': purchase.created_at.isoformat() if purchase and purchase.created_at else None,
            'restaurant_name': purchase.restaurant.name if purchase and getattr(purchase, 'restaurant', None) else None,
            'raw_material_name': raw.name if raw else '—',
            'unit_symbol': (raw.unit.symbol or raw.unit.name) if raw and getattr(raw, 'unit', None) else '',
            'quantity': str(item.quantity),
            'unit_price': str(item.price),
            'total': str(item.total),
        })

    # Supply frequency (distinct purchase dates in last 90 days)
    supply_frequency_count = (
        PurchaseItem.objects.filter(raw_material__vendor_id=v.id, purchase__created_at__date__gte=since)
        .values('purchase__created_at__date')
        .distinct()
        .count()
    )
    supply_frequency = {'distinct_supply_days_90d': supply_frequency_count}

    payload = {
        **_vendor_to_dict(v),
        'stats': stats,
        'restaurant_supplied': restaurant_supplied,
        'supply_trend': supply_trend,
        'material_wise_supply': material_wise_supply,
        'paid_total': paid_total,
        'due_total': due_total,
        'payment_history': payment_history,
        'supply_transactions': supply_transactions,
        'supply_frequency': supply_frequency,
    }
    return JsonResponse(payload)
