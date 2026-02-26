"""Waiter profile: user + staff info, salary (view-only), feedback QR URL, attendance history."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from core.models import Attendance, Staff
from core.utils import get_waiter_staff_id


def _attendance_to_dict(a):
    return {
        'id': a.id,
        'date': a.date.isoformat() if a.date else None,
        'status': a.status,
        'leave_reason': a.leave_reason or '',
    }


@require_http_methods(['GET'])
def waiter_profile(request):
    """
    Return waiter profile: user info, staff info, salary (view-only), feedback URL for QR, attendance history.
    """
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    staff = Staff.objects.filter(pk=staff_id).select_related('user', 'restaurant').first()
    if not staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    user = staff.user
    restaurant = staff.restaurant

    role = 'Waiter'
    if getattr(staff, 'is_manager', False):
        role = 'Manager' if not getattr(staff, 'is_waiter', False) else 'Waiter'

    salary = None
    if staff.salary is not None:
        salary = str(staff.salary)
    per_day_salary = str(staff.per_day_salary) if staff.per_day_salary is not None else None

    # Public feedback form URL: /restaurant/<slug>/feedback?staff_id=<id> (customer scans waiter QR)
    feedback_path = f'/restaurant/{restaurant.slug}/feedback?staff_id={staff.id}'
    feedback_url = request.build_absolute_uri(feedback_path) if request else feedback_path

    attendance_qs = Attendance.objects.filter(staff_id=staff_id).order_by('-date')[:30]
    attendance_history = [_attendance_to_dict(a) for a in attendance_qs]

    data = {
        'user': {
            'name': getattr(user, 'name', '') or getattr(user, 'username', ''),
            'phone': getattr(user, 'phone', ''),
        },
        'staff': {
            'id': staff.id,
            'designation': staff.designation or '',
            'role': role,
            'salary': salary,
            'per_day_salary': per_day_salary,
            'joined_at': staff.joined_at.isoformat() if staff.joined_at else None,
            'restaurant_name': restaurant.name if restaurant else None,
        },
        'feedback_url': feedback_url,
        'feedback_path': feedback_path,
        'attendance_history': attendance_history,
    }
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(['PUT', 'PATCH'])
def waiter_profile_update(request):
    """
    Update waiter profile. Accepts fcm_token to set on request.user (for FCM notifications).
    """
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    user = request.user
    if 'fcm_token' in body:
        user.fcm_token = (body.get('fcm_token') or '').strip()[:255]
        user.save(update_fields=['fcm_token', 'updated_at'])
    return JsonResponse({'ok': True})
