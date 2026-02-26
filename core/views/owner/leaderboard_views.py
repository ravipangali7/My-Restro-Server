"""Owner leaderboard: staff aggregated by orders, sales, served, rating, tips, attendance. Function-based."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Avg, Q

from core.models import Staff, Feedback
from core.utils import get_restaurant_ids, auth_required


# Use string values to avoid circular import; models use TextChoices
PAID_STATUSES = ('paid', 'success')
SERVED_STATUS = 'served'
PRESENT_STATUS = 'present'


@auth_required
@require_http_methods(['GET'])
def owner_leaderboard(request):
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'results': [], 'team_avg': {}})

    staff_qs = (
        Staff.objects.filter(restaurant_id__in=rid)
        .select_related('user', 'restaurant')
        .annotate(
            orders_count=Count('served_orders'),
            revenue=Sum(
                'served_orders__total',
                filter=Q(served_orders__payment_status__in=PAID_STATUSES),
            ),
            served_count=Count(
                'served_orders',
                filter=Q(served_orders__status=SERVED_STATUS),
            ),
            attendance_days=Count(
                'attendances',
                filter=Q(attendances__status=PRESENT_STATUS),
            ),
        )
    )

    # Build list with rating (Feedback is separate) and sort by performance score
    results = []
    for s in staff_qs:
        feedbacks = Feedback.objects.filter(staff_id=s.id)
        rating_avg = feedbacks.aggregate(a=Avg('rating'))['a']
        rating_count = feedbacks.count()
        rev = (s.revenue or 0)
        tips = 0  # No Tip model yet
        score = float(rev) + float(tips)
        results.append({
            'staff_id': s.id,
            'user_id': s.user_id,
            'user_name': getattr(s.user, 'name', None) or getattr(s.user, 'username', ''),
            'restaurant_name': s.restaurant.name if s.restaurant else None,
            'image': getattr(s.user, 'image', None).url if getattr(s.user, 'image', None) else None,
            'orders_count': s.orders_count or 0,
            'sales': str(s.revenue or 0),
            'revenue': str(s.revenue or 0),
            'served_count': s.served_count or 0,
            'tips': str(tips),
            'attendance_days': s.attendance_days or 0,
            'rating': float(rating_avg) if rating_avg is not None else 0,
            'rating_count': rating_count,
            '_score': score,
        })

    # Sort by score (revenue + tips) descending, then by orders_count
    results.sort(key=lambda x: (-x['_score'], -x['orders_count']))
    for i, r in enumerate(results, start=1):
        r['rank'] = i
        del r['_score']

    total_orders = sum(r['orders_count'] for r in results)
    total_rating = sum(r['rating'] * r['rating_count'] for r in results)
    total_rating_count = sum(r['rating_count'] for r in results)
    total_revenue = sum(float(r['sales']) for r in results)
    team_avg = {
        'avg_orders_per_day': total_orders / 7 if results else 0,
        'avg_rating': total_rating / total_rating_count if total_rating_count else 0,
        'avg_revenue': total_revenue / len(results) if results else 0,
    }
    return JsonResponse({'results': results, 'team_avg': team_avg})
