"""Super Admin global customers list. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Q, Count, Value
from django.db.models.functions import Coalesce

from core.models import Customer, CustomerRestaurant, Order, OrderStatus
from core.utils import paginate_queryset, parse_date


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
    """List all customers with aggregates (to_pay, to_receive, order_count, total_spent). Paginated."""
    search = (request.GET.get('search') or '').strip()
    qs = Customer.objects.all().order_by('-created_at')
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(address__icontains=search)
        )
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    if start_date:
        qs = qs.filter(created_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(created_at__date__lte=end_date)
    qs = qs.annotate(
        _to_pay=Coalesce(Sum('restaurant_links__to_pay'), Value(Decimal('0'))),
        _to_receive=Coalesce(Sum('restaurant_links__to_receive'), Value(Decimal('0'))),
        _order_count=Count('orders', distinct=True),
        _total_spent=Coalesce(Sum('orders__total', filter=~Q(orders__status=OrderStatus.REJECTED)), Value(Decimal('0'))),
    ).order_by('-created_at')
    total_count = qs.count()
    total_to_pay = CustomerRestaurant.objects.aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
    total_to_receive = CustomerRestaurant.objects.aggregate(s=Sum('to_receive'))['s'] or Decimal('0')
    stats = {
        'total': total_count,
        'total_to_pay': str(total_to_pay),
        'total_to_receive': str(total_to_receive),
    }
    qs_paged, pagination = paginate_queryset(qs, request, default_page_size=20)
    results = []
    for c in qs_paged:
        extra = {
            'to_pay': str(getattr(c, '_to_pay', None) or Decimal('0')),
            'to_receive': str(getattr(c, '_to_receive', None) or Decimal('0')),
            'order_count': getattr(c, '_order_count', 0) or 0,
            'total_spent': str(getattr(c, '_total_spent', None) or Decimal('0')),
        }
        results.append(_customer_to_dict(c, extra))
    return JsonResponse({'stats': stats, 'results': results, 'pagination': pagination})
