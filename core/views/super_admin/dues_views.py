"""Super Admin dues list: restaurants with due_balance and threshold. Function-based."""
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from core.models import Restaurant, SuperSetting, Order, OrderStatus


@require_http_methods(['GET'])
def super_admin_dues_list(request):
    """List restaurants with due_balance, due_threshold, over_threshold flag; optional revenue/order stats."""
    ss = SuperSetting.objects.first()
    threshold = (ss.due_threshold or Decimal('0')) if ss else Decimal('0')
    qs = Restaurant.objects.all().select_related('user').order_by('-due_balance')
    results = []
    total_due = Decimal('0')
    over_count = 0
    for r in qs:
        due = r.due_balance or Decimal('0')
        total_due += due
        over = due > threshold
        if over:
            over_count += 1
        rev = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED).aggregate(
            s=Sum('total')
        )['s'] or Decimal('0')
        order_count = Order.objects.filter(restaurant=r).count()
        results.append({
            'id': r.id,
            'name': r.name,
            'slug': r.slug,
            'due_balance': str(due),
            'due_threshold': str(threshold),
            'over_threshold': over,
            'revenue': str(rev),
            'order_count': order_count,
            'owner_name': getattr(r.user, 'name', '') or getattr(r.user, 'username', '') if r.user_id else '',
        })
    stats = {
        'total_restaurants': len(results),
        'total_due': str(total_due),
        'due_threshold': str(threshold),
        'over_threshold_count': over_count,
    }
    return JsonResponse({'stats': stats, 'results': results})
