"""Waiter tables list (read-only). Only tables assigned to this waiter."""
from django.http import JsonResponse

from core.models import Table
from core.permissions import get_waiter_restaurant
from core.utils import get_waiter_staff_id


def _table_to_dict(t):
    return {
        'id': t.id,
        'restaurant_id': t.restaurant_id,
        'name': t.name,
        'capacity': t.capacity,
        'floor': t.floor or '',
        'near_by': t.near_by or '',
        'notes': getattr(t, 'notes', '') or '',
    }


def waiter_table_list(request):
    restaurant = get_waiter_restaurant(request)
    staff_id = get_waiter_staff_id(request)
    if not restaurant or not staff_id:
        return JsonResponse({'results': []})
    qs = (
        Table.objects.filter(restaurant=restaurant, assigned_waiters__id=staff_id)
        .distinct()
        .order_by('floor', 'name')
    )
    results = [_table_to_dict(t) for t in qs]
    return JsonResponse({'results': results})
