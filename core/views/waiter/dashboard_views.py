"""Function-based views for waiter dashboard. Personal-only metrics; no restaurant-wide data."""
from django.http import JsonResponse
from django.db.models import Sum, Avg
from django.utils import timezone
from decimal import Decimal

from core.models import Order, OrderStatus, PaymentStatus, Attendance, Feedback, Table, Staff
from core.utils import get_waiter_staff_id
from core.permissions import get_waiter_restaurant


def _decimal_str(d):
    if d is None:
        return '0'
    return str(Decimal(d))


def waiter_dashboard(request):
    """
    Waiter dashboard: personal only.
    Returns: today_my_orders_count, today_my_sales, my_attendance_today, my_performance_score, last_5_orders.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    restaurant = get_waiter_restaurant(request)
    tables_count = Table.objects.filter(restaurant=restaurant).count() if restaurant else 0
    feedback_count = Feedback.objects.filter(staff_id=staff_id).count()

    today = timezone.now().date()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    orders = Order.objects.filter(waiter_id=staff_id)
    orders_non_rejected = orders.exclude(status=OrderStatus.REJECTED)
    orders_today = orders_non_rejected.filter(created_at__gte=today_start)

    today_my_orders_count = orders_today.count()
    today_my_sales = orders_today.aggregate(s=Sum('total'))['s'] or Decimal('0')
    total_orders_handled = orders_non_rejected.count()
    total_sales_handled = orders_non_rejected.aggregate(s=Sum('total'))['s'] or Decimal('0')

    my_attendance_today = None
    att = Attendance.objects.filter(staff_id=staff_id, date=today).first()
    if att:
        my_attendance_today = att.status

    feedback_agg = Feedback.objects.filter(staff_id=staff_id).aggregate(
        avg_rating=Avg('rating'),
    )
    avg_rating = feedback_agg['avg_rating']
    my_performance_score = float(avg_rating) if avg_rating is not None else 0.0

    staff = Staff.objects.filter(pk=staff_id).first()
    salary = str(staff.salary) if staff and staff.salary is not None else None
    per_day_salary = str(staff.per_day_salary) if staff and staff.per_day_salary is not None else None

    last_5_orders_qs = orders.select_related('table').prefetch_related('items').order_by('-created_at')[:5]
    last_5_orders = []
    for o in last_5_orders_qs:
        items_summary = []
        for oi in o.items.all()[:5]:
            name = None
            if oi.product:
                name = oi.product.name
            elif oi.combo_set:
                name = oi.combo_set.name
            if name:
                items_summary.append({
                    'name': name,
                    'quantity': str(oi.quantity),
                    'price': _decimal_str(oi.price),
                    'total': _decimal_str(oi.total),
                })
        last_5_orders.append({
            'id': o.id,
            'table_id': o.table_id,
            'table_name': o.table.name if o.table else None,
            'total': _decimal_str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'items': items_summary,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        })

    data = {
        'today_my_orders_count': today_my_orders_count,
        'today_my_sales': _decimal_str(today_my_sales),
        'total_orders_handled': total_orders_handled,
        'total_sales_handled': _decimal_str(total_sales_handled),
        'my_attendance_today': my_attendance_today,
        'my_performance_score': round(my_performance_score, 1),
        'salary': salary,
        'per_day_salary': per_day_salary,
        'last_5_orders': last_5_orders,
        'tables_count': tables_count,
        'feedback_count': feedback_count,
    }

    return JsonResponse(data)
