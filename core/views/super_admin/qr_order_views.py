"""Super Admin QR stand orders list, create, detail, update, delete. Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta

from django.db.models import Q

from core.models import QrStandOrder, Restaurant, Transaction, TransactionCategory, SuperSetting, PaymentStatus
from core.utils import auth_required, paginate_queryset


def _require_super_admin(request):
    if not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Super admin required'}, status=403)
    return None


def _qr_order_to_dict(q):
    return {
        'id': q.id,
        'restaurant_id': q.restaurant_id,
        'restaurant_name': q.restaurant.name if q.restaurant else None,
        'restaurant_logo': q.restaurant.logo.url if q.restaurant and q.restaurant.logo else None,
        'quantity': q.quantity,
        'total': str(q.total),
        'status': q.status,
        'payment_status': q.payment_status,
        'created_at': q.created_at.isoformat() if q.created_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def super_admin_qr_order_list(request):
    err = _require_super_admin(request)
    if err:
        return err
    qs = QrStandOrder.objects.all().select_related('restaurant').order_by('-created_at')
    restaurant_id = request.GET.get('restaurant_id')
    if restaurant_id:
        qs = qs.filter(restaurant_id=restaurant_id)
    date_from = request.GET.get('date_from') or request.GET.get('start_date')
    date_to = request.GET.get('date_to') or request.GET.get('end_date')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(restaurant__name__icontains=search) | Q(restaurant__slug__icontains=search))
    total_orders = qs.count()
    pending = qs.filter(status='pending').count()
    accepted = qs.filter(status='accepted').count()
    delivered = qs.filter(status='delivered').count()
    revenue = qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    total_quantity_sold = qs.aggregate(s=Sum('quantity'))['s'] or 0
    paid_qs = qs.filter(payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS])
    paid_count = paid_qs.count()
    paid_revenue = paid_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')
    stats = {
        'total_orders': total_orders,
        'pending': pending,
        'accepted': accepted,
        'delivered': delivered,
        'revenue': str(revenue),
        'total_quantity_sold': int(total_quantity_sold),
        'paid_count': paid_count,
        'paid_revenue': str(paid_revenue),
    }
    # Total QR revenue from system transactions (transaction impact)
    qr_system_revenue = (
        Transaction.objects.filter(is_system=True, category=TransactionCategory.QR_STAND_ORDER)
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )
    transaction_breakdown = {
        'total_qr_revenue_system': str(qr_system_revenue),
    }
    # Revenue time series: daily sum of QrStandOrder.total for last 30 days
    start_ts = timezone.now() - timedelta(days=30)
    daily_qs = (
        QrStandOrder.objects.filter(created_at__gte=start_ts)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(value=Sum('total'))
        .order_by('day')
    )
    revenue_time_series = [
        {'name': row['day'].isoformat() if row.get('day') else '', 'value': float(row.get('value') or 0)}
        for row in daily_qs
    ]
    qs_paged, pagination = paginate_queryset(qs, request)
    results = [_qr_order_to_dict(q) for q in qs_paged]
    return JsonResponse({
        'stats': stats,
        'results': results,
        'pagination': pagination,
        'transaction_breakdown': transaction_breakdown,
        'revenue_time_series': revenue_time_series,
    })


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_qr_order_create(request):
    err = _require_super_admin(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    restaurant_id = body.get('restaurant_id')
    if not restaurant_id:
        return JsonResponse({'error': 'restaurant_id required'}, status=400)
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    if not getattr(restaurant, 'is_restaurant', True):
        return JsonResponse({'error': 'Restaurant is inactive'}, status=403)
    quantity = int(body.get('quantity', 1))
    total = Decimal(str(body.get('total', 0)))
    q = QrStandOrder(
        restaurant=restaurant,
        quantity=quantity,
        total=total,
        status=body.get('status', 'pending'),
        payment_status=body.get('payment_status', 'pending'),
    )
    q.save()
    return JsonResponse(_qr_order_to_dict(q), status=201)


@auth_required
@require_http_methods(['GET'])
def super_admin_qr_order_detail(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    q = get_object_or_404(QrStandOrder, pk=pk)
    data = _qr_order_to_dict(q)
    ss = SuperSetting.objects.first()
    data['super_setting_impact'] = {
        'per_qr_stand_price': str(ss.per_qr_stand_price) if ss and ss.per_qr_stand_price is not None else '0',
    } if ss else {'per_qr_stand_price': '0'}
    data['transaction_impact'] = None
    return JsonResponse(data)


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_qr_order_update(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    q = get_object_or_404(QrStandOrder, pk=pk)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    if 'restaurant_id' in body:
        q.restaurant = get_object_or_404(Restaurant, pk=body['restaurant_id'])
    if 'quantity' in body:
        q.quantity = int(body['quantity'])
    if 'total' in body:
        q.total = Decimal(str(body['total']))
    if 'status' in body:
        q.status = body['status']
    if 'payment_status' in body:
        q.payment_status = body['payment_status']
    q.save()
    return JsonResponse(_qr_order_to_dict(q))


@csrf_exempt
@auth_required
@require_http_methods(['DELETE'])
def super_admin_qr_order_delete(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    q = get_object_or_404(QrStandOrder, pk=pk)
    q.delete()
    return JsonResponse({'success': True})
