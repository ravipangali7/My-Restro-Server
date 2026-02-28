"""Owner paid records and received records list and create. Function-based."""
import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Q

from core.models import PaidRecord, ReceivedRecord, Restaurant, Vendor, Purchase, Expenses, Staff, Customer, Order
from core.utils import get_restaurant_ids, auth_required, paginate_queryset, parse_date


def _paid_to_dict(p):
    return {
        'id': p.id,
        'restaurant_id': p.restaurant_id,
        'name': p.name,
        'amount': str(p.amount),
        'vendor_id': p.vendor_id,
        'payment_method': p.payment_method or '',
        'remarks': p.remarks or '',
        'created_at': p.created_at.isoformat() if p.created_at else None,
    }


def _received_to_dict(r):
    return {
        'id': r.id,
        'restaurant_id': r.restaurant_id,
        'name': r.name,
        'amount': str(r.amount),
        'customer_id': r.customer_id,
        'payment_method': r.payment_method or '',
        'remarks': r.remarks or '',
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def owner_paid_list(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'stats': {'total_paid': '0'}, 'results': [], 'pagination': {'page': 1, 'page_size': 20, 'total_count': 0}})
    qs = PaidRecord.objects.filter(restaurant_id__in=rid).select_related('vendor')
    start_date = parse_date(request.GET.get('start_date') or request.GET.get('date_from'))
    end_date = parse_date(request.GET.get('end_date') or request.GET.get('date_to'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(remarks__icontains=search)
            | Q(vendor__name__icontains=search)
        )
    total = qs.aggregate(s=Sum('amount'))['s']
    stats = {'total_paid': str(total or 0)}
    qs_paged, pagination = paginate_queryset(qs.order_by('-created_at'), request, default_page_size=20)
    results = [_paid_to_dict(p) for p in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@auth_required
@require_http_methods(['GET'])
def owner_received_list(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'stats': {'total_received': '0'}, 'results': [], 'pagination': {'page': 1, 'page_size': 20, 'total_count': 0}})
    qs = ReceivedRecord.objects.filter(restaurant_id__in=rid).select_related('customer')
    start_date = parse_date(request.GET.get('start_date') or request.GET.get('date_from'))
    end_date = parse_date(request.GET.get('end_date') or request.GET.get('date_to'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    search = (request.GET.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(remarks__icontains=search)
            | Q(customer__name__icontains=search)
        )
    total = qs.aggregate(s=Sum('amount'))['s']
    stats = {'total_received': str(total or 0)}
    qs_paged, pagination = paginate_queryset(qs.order_by('-created_at'), request, default_page_size=20)
    results = [_received_to_dict(r) for r in qs_paged]
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_paid_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
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
        amount = Decimal(str(body.get('amount', 0)))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid amount'}, status=400)
    if amount <= 0:
        return JsonResponse({'error': 'Amount must be positive'}, status=400)
    vendor_id = body.get('vendor_id')
    purchase_id = body.get('purchase_id')
    expenses_id = body.get('expenses_id')
    staff_id = body.get('staff_id')
    payment_method = (body.get('payment_method') or '')[:20]
    remarks = (body.get('remarks') or '')[:2000]
    p = PaidRecord(
        restaurant=restaurant,
        name=name,
        amount=amount,
        vendor_id=vendor_id or None,
        purchase_id=purchase_id or None,
        expenses_id=expenses_id or None,
        staff_id=staff_id or None,
        payment_method=payment_method or None,
        remarks=remarks,
    )
    p.save()
    return JsonResponse(_paid_to_dict(p), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_received_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
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
        amount = Decimal(str(body.get('amount', 0)))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid amount'}, status=400)
    if amount <= 0:
        return JsonResponse({'error': 'Amount must be positive'}, status=400)
    customer_id = body.get('customer_id')
    order_id = body.get('order_id')
    payment_method = (body.get('payment_method') or '')[:20]
    remarks = (body.get('remarks') or '')[:2000]
    r = ReceivedRecord(
        restaurant=restaurant,
        name=name,
        amount=amount,
        customer_id=customer_id or None,
        order_id=order_id or None,
        payment_method=payment_method or None,
        remarks=remarks,
    )
    r.save()
    return JsonResponse(_received_to_dict(r), status=201)
