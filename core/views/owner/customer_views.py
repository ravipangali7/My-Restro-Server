"""Owner customers list and detail (scoped by restaurant). Function-based."""
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum

from core.models import Customer, CustomerRestaurant, Order, Restaurant
from core.utils import get_restaurant_ids, auth_required


def _customer_to_dict(c, extra=None):
    d = {
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'country_code': getattr(c, 'country_code', '') or '',
        'address': c.address or '',
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'updated_at': c.updated_at.isoformat() if c.updated_at else None,
    }
    if extra:
        d.update(extra)
    return d


@auth_required
@require_http_methods(['GET'])
def owner_customer_list(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'stats': {}, 'results': []})
    if getattr(request.user, 'is_superuser', False):
        restaurant_ids = list(Restaurant.objects.values_list('id', flat=True))
    else:
        restaurant_ids = rid
    links = CustomerRestaurant.objects.filter(restaurant_id__in=restaurant_ids).select_related('customer')
    customer_ids = list(links.values_list('customer_id', flat=True).distinct())
    order_customer_ids = list(Order.objects.filter(restaurant_id__in=restaurant_ids).exclude(customer_id__isnull=True).values_list('customer_id', flat=True).distinct())
    all_customer_ids = list(set(customer_ids) | set(order_customer_ids))
    if not all_customer_ids:
        return JsonResponse({'stats': {'total': 0, 'vip': 0, 'credit': 0, 'due': 0}, 'results': []})
    customers = Customer.objects.filter(id__in=all_customer_ids)
    results = []
    vip_count = 0
    for c in customers:
        cr = CustomerRestaurant.objects.filter(customer=c, restaurant_id__in=restaurant_ids).aggregate(to_pay=Sum('to_pay'), to_receive=Sum('to_receive'))
        order_count = Order.objects.filter(restaurant_id__in=restaurant_ids, customer=c).count()
        total_spent = Order.objects.filter(restaurant_id__in=restaurant_ids, customer=c).aggregate(s=Sum('total'))['s']
        if order_count >= 50:
            vip_count += 1
        extra = {
            'to_pay': str(cr['to_pay'] or 0),
            'to_receive': str(cr['to_receive'] or 0),
            'order_count': order_count,
            'total_spent': str(total_spent or 0),
        }
        results.append(_customer_to_dict(c, extra))
    total_due = sum(Decimal(r['to_pay']) for r in results)
    stats = {'total': len(results), 'vip': vip_count, 'credit': str(total_due), 'due': str(total_due)}
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_customer_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    phone = (body.get('phone') or '').strip()
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        restaurant_ids = list(Restaurant.objects.values_list('id', flat=True))
    else:
        restaurant_ids = list(rid) if rid else []
    if not restaurant_ids:
        return JsonResponse({'error': 'No restaurant to link customer to'}, status=400)
    customer = Customer.objects.create(
        name=name,
        phone=phone,
        country_code=(body.get('country_code') or '')[:10],
        address=(body.get('address') or '')[:2000],
    )
    for rest_id in restaurant_ids:
        CustomerRestaurant.objects.get_or_create(
            customer=customer,
            restaurant_id=rest_id,
            defaults={'to_pay': Decimal('0'), 'to_receive': Decimal('0')},
        )
    return JsonResponse(_customer_to_dict(customer, {
        'to_pay': '0',
        'to_receive': '0',
        'order_count': 0,
        'total_spent': '0',
    }), status=201)


@auth_required
@require_http_methods(['GET'])
def owner_customer_detail(request, pk):
    c = get_object_or_404(Customer, pk=pk)
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    restaurant_ids = list(Restaurant.objects.values_list('id', flat=True)) if getattr(request.user, 'is_superuser', False) else rid
    links = CustomerRestaurant.objects.filter(customer=c, restaurant_id__in=restaurant_ids)
    if not links.exists() and not Order.objects.filter(customer=c, restaurant_id__in=restaurant_ids).exists():
        return JsonResponse({'error': 'Forbidden'}, status=403)
    cr = links.aggregate(to_pay=Sum('to_pay'), to_receive=Sum('to_receive'))
    order_count = Order.objects.filter(restaurant_id__in=restaurant_ids, customer=c).count()
    total_spent = Order.objects.filter(restaurant_id__in=restaurant_ids, customer=c).aggregate(s=Sum('total'))['s']
    extra = {
        'to_pay': str(cr['to_pay'] or 0),
        'to_receive': str(cr['to_receive'] or 0),
        'order_count': order_count,
        'total_spent': str(total_spent or 0),
    }
    return JsonResponse(_customer_to_dict(c, extra))
