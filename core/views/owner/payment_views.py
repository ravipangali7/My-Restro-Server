"""Owner payment endpoints: subscription, QR stand order, due balance. No owner_unlocked so owner can pay when locked."""
import json
from decimal import Decimal
from datetime import date
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import Restaurant, QrStandOrder, SuperSetting
from core.utils import get_restaurant_ids, auth_required
from core.permissions import owner_required
from core.services import pay_subscription_fee, pay_qr_stand_order, pay_due_balance


@csrf_exempt
@auth_required
@owner_required
@require_http_methods(['POST'])
def owner_pay_subscription(request):
    """
    POST body: restaurant_id (int) or restaurant_ids (list), optional amount (default from SuperSetting).
    Validate restaurant(s) in get_restaurant_ids(request). Call pay_subscription_fee for each.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    allowed_ids = get_restaurant_ids(request)
    if not allowed_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    restaurant_ids = []
    if 'restaurant_id' in body:
        restaurant_ids = [int(body['restaurant_id'])]
    elif 'restaurant_ids' in body:
        restaurant_ids = [int(x) for x in body['restaurant_ids']]
    else:
        return JsonResponse({'error': 'restaurant_id or restaurant_ids required'}, status=400)

    for rid in restaurant_ids:
        if rid not in allowed_ids and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({'error': f'Restaurant {rid} not allowed'}, status=403)

    amount = None
    if body.get('amount') is not None:
        try:
            amount = Decimal(str(body['amount']))
        except Exception:
            return JsonResponse({'error': 'Invalid amount'}, status=400)

    results = []
    for rid in restaurant_ids:
        restaurant = get_object_or_404(Restaurant, pk=rid)
        try:
            pay_subscription_fee(restaurant, amount)
            results.append({'restaurant_id': rid, 'success': True})
        except Exception as e:
            results.append({'restaurant_id': rid, 'success': False, 'error': str(e)})

    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@owner_required
@require_http_methods(['POST'])
def owner_pay_qr_stand(request):
    """
    POST body: qr_stand_order_id (int) or qr_stand_order_ids (list).
    Validate each order's restaurant belongs to owner. Call pay_qr_stand_order for each.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    allowed_ids = get_restaurant_ids(request)
    if not allowed_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    order_ids = []
    if 'qr_stand_order_id' in body:
        order_ids = [int(body['qr_stand_order_id'])]
    elif 'qr_stand_order_ids' in body:
        order_ids = [int(x) for x in body['qr_stand_order_ids']]
    else:
        return JsonResponse({'error': 'qr_stand_order_id or qr_stand_order_ids required'}, status=400)

    results = []
    for oid in order_ids:
        order = get_object_or_404(QrStandOrder, pk=oid)
        if order.restaurant_id not in allowed_ids and not getattr(request.user, 'is_superuser', False):
            results.append({'qr_stand_order_id': oid, 'success': False, 'error': 'Forbidden'})
            continue
        try:
            pay_qr_stand_order(order)
            results.append({'qr_stand_order_id': oid, 'success': True})
        except Exception as e:
            results.append({'qr_stand_order_id': oid, 'success': False, 'error': str(e)})

    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@owner_required
@require_http_methods(['POST'])
def owner_pay_due(request):
    """
    POST body: restaurant_id (int) and amount, or payments: [{ restaurant_id, amount }, ...].
    Validate ownership. Call pay_due_balance for each.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    allowed_ids = get_restaurant_ids(request)
    if not allowed_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    payments = []
    if 'restaurant_id' in body and 'amount' in body:
        payments = [{'restaurant_id': int(body['restaurant_id']), 'amount': Decimal(str(body['amount']))}]
    elif 'payments' in body:
        for p in body['payments']:
            rid = int(p.get('restaurant_id'))
            amt = Decimal(str(p.get('amount', 0)))
            payments.append({'restaurant_id': rid, 'amount': amt})
    else:
        return JsonResponse({'error': 'restaurant_id and amount, or payments list required'}, status=400)

    for p in payments:
        if p['restaurant_id'] not in allowed_ids and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({'error': f"Restaurant {p['restaurant_id']} not allowed"}, status=403)

    results = []
    for p in payments:
        restaurant = get_object_or_404(Restaurant, pk=p['restaurant_id'])
        try:
            pay_due_balance(restaurant, p['amount'])
            results.append({'restaurant_id': p['restaurant_id'], 'success': True})
        except Exception as e:
            results.append({'restaurant_id': p['restaurant_id'], 'success': False, 'error': str(e)})

    return JsonResponse({'results': results})


@auth_required
@owner_required
@require_http_methods(['GET'])
def owner_subscription_preview(request):
    """
    GET ?restaurant_ids=1,2,3 → breakdown (restaurant_id, name, amount, month, year), total, period_month, period_year.
    """
    allowed_ids = get_restaurant_ids(request)
    if not allowed_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    raw = request.GET.get('restaurant_ids', '')
    restaurant_ids = [int(x.strip()) for x in raw.split(',') if x.strip()]
    if not restaurant_ids:
        return JsonResponse({'breakdown': [], 'total': '0', 'period_month': None, 'period_year': None})

    for rid in restaurant_ids:
        if rid not in allowed_ids and not getattr(request.user, 'is_superuser', False):
            return JsonResponse({'error': f'Restaurant {rid} not allowed'}, status=403)

    ss = SuperSetting.objects.first()
    fee = (ss.subscription_fee_per_month or Decimal('0')) if ss else Decimal('0')
    today = date.today()
    period_month = today.month
    period_year = today.year

    breakdown = []
    for rid in restaurant_ids:
        r = Restaurant.objects.filter(pk=rid).first()
        breakdown.append({
            'restaurant_id': rid,
            'name': r.name if r else f'Restaurant #{rid}',
            'amount': str(fee),
            'month': period_month,
            'year': period_year,
        })
    total = fee * len(restaurant_ids)
    return JsonResponse({
        'breakdown': breakdown,
        'total': str(total),
        'period_month': period_month,
        'period_year': period_year,
    })


@auth_required
@owner_required
@require_http_methods(['GET'])
def owner_qr_stand_preview(request):
    """
    GET ?qr_stand_order_ids=1,2,3 → breakdown (qr_stand_order_id, restaurant_name, total, fee), total_amount, total_fee.
    """
    allowed_ids = get_restaurant_ids(request)
    if not allowed_ids and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'No restaurants'}, status=403)

    raw = request.GET.get('qr_stand_order_ids', '')
    order_ids = [int(x.strip()) for x in raw.split(',') if x.strip()]
    if not order_ids:
        return JsonResponse({'breakdown': [], 'total_amount': '0', 'total_fee': '0'})

    ss = SuperSetting.objects.first()
    fee_per_order = (ss.per_qr_stand_price or Decimal('0')) if ss else Decimal('0')

    breakdown = []
    total_amount = Decimal('0')
    for oid in order_ids:
        order = QrStandOrder.objects.filter(pk=oid).select_related('restaurant').first()
        if not order:
            continue
        if order.restaurant_id not in allowed_ids and not getattr(request.user, 'is_superuser', False):
            continue
        total_amount += order.total or Decimal('0')
        breakdown.append({
            'qr_stand_order_id': order.id,
            'restaurant_name': order.restaurant.name if order.restaurant_id and order.restaurant else None,
            'total': str(order.total or '0'),
            'fee': str(fee_per_order),
        })
    total_fee = fee_per_order * len(breakdown)
    return JsonResponse({
        'breakdown': breakdown,
        'total_amount': str(total_amount),
        'total_fee': str(total_fee),
    })
