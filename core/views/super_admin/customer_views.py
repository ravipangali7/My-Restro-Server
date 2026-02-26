"""Super Admin global customers list. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Q

from core.models import Customer, CustomerRestaurant, Order


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


@require_http_methods(['GET'])
def super_admin_customer_list(request):
    """List all customers with aggregates (to_pay, to_receive, order_count, total_spent)."""
    search = (request.GET.get('search') or '').strip()
    qs = Customer.objects.all().order_by('-created_at')
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(address__icontains=search)
        )
    qs = qs[:200]
    results = []
    total_to_pay = Decimal('0')
    total_to_receive = Decimal('0')
    for c in qs:
        cr_agg = CustomerRestaurant.objects.filter(customer=c).aggregate(
            to_pay=Sum('to_pay'), to_receive=Sum('to_receive')
        )
        order_count = Order.objects.filter(customer=c).count()
        total_spent = Order.objects.filter(customer=c).exclude(status='rejected').aggregate(
            s=Sum('total')
        )['s'] or Decimal('0')
        to_pay = cr_agg['to_pay'] or Decimal('0')
        to_receive = cr_agg['to_receive'] or Decimal('0')
        total_to_pay += to_pay
        total_to_receive += to_receive
        extra = {
            'to_pay': str(to_pay),
            'to_receive': str(to_receive),
            'order_count': order_count,
            'total_spent': str(total_spent),
        }
        results.append(_customer_to_dict(c, extra))
    stats = {
        'total': len(results),
        'total_to_pay': str(total_to_pay),
        'total_to_receive': str(total_to_receive),
    }
    return JsonResponse({'stats': stats, 'results': results})
