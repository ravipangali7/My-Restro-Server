"""Waiter attendance: view own only. Read-only; no create/update."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import Attendance
from core.utils import get_waiter_staff_id


def _attendance_to_dict(a):
    return {
        'id': a.id,
        'restaurant_id': a.restaurant_id,
        'date': a.date.isoformat() if a.date else None,
        'status': a.status,
        'leave_reason': a.leave_reason or '',
        'created_at': a.created_at.isoformat() if a.created_at else None,
    }


@require_http_methods(['GET'])
def waiter_attendance_list(request):
    """List attendance records for the current waiter only. No mark/modify."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'results': []})
    qs = Attendance.objects.filter(staff_id=staff_id).order_by('-date')
    limit = min(int(request.GET.get('limit', 100)), 200)
    results = [_attendance_to_dict(a) for a in qs[:limit]]
    return JsonResponse({'results': results})
