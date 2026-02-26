"""Manager attendance list by date, set present/absent/leave. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Count
from datetime import datetime
from calendar import monthrange

from core.models import Attendance, Staff
from core.utils import get_restaurant_ids, auth_required


def _attendance_to_dict(a):
    return {
        'id': a.id,
        'restaurant_id': a.restaurant_id,
        'date': a.date.isoformat() if a.date else None,
        'staff_id': a.staff_id,
        'staff_name': getattr(a.staff.user, 'name', '') if a.staff and getattr(a.staff, 'user', None) else '',
        'staff_image': a.staff.user.image.url if a.staff and getattr(a.staff, 'user', None) and getattr(a.staff.user, 'image', None) and a.staff.user.image else None,
        'status': a.status,
        'leave_reason': a.leave_reason or '',
        'created_at': a.created_at.isoformat() if a.created_at else None,
    }


@require_http_methods(['GET'])
def manager_attendance_list(request):
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'stats': {}, 'results': []})
    qs = Attendance.objects.filter(restaurant_id__in=rid).select_related('staff__user')
    date = request.GET.get('date')
    if date:
        qs = qs.filter(date=date)
    present = qs.filter(status='present').count()
    absent = qs.filter(status='absent').count()
    leave = qs.filter(status='leave').count()
    stats = {'present': present, 'absent': absent, 'leave': leave}
    results = [_attendance_to_dict(a) for a in qs.order_by('-date', 'staff__user__name')[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST', 'PATCH', 'PUT'])
def manager_attendance_set(request):
    """Set attendance for a staff on a date. POST body: staff_id, date, status (present|absent|leave), leave_reason?"""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    staff_id = body.get('staff_id')
    date_str = body.get('date')
    status = body.get('status', 'present')
    if not staff_id or not date_str:
        return JsonResponse({'error': 'staff_id and date required'}, status=400)
    staff = get_object_or_404(Staff, pk=staff_id, restaurant_id__in=rid)
    try:
        d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date'}, status=400)
    att, _ = Attendance.objects.get_or_create(
        restaurant=staff.restaurant,
        staff=staff,
        date=d,
        defaults={'status': status, 'leave_reason': body.get('leave_reason', '')}
    )
    if not _:
        att.status = status
        att.leave_reason = body.get('leave_reason', '')
        att.save()
    return JsonResponse(_attendance_to_dict(att))


@auth_required
@require_http_methods(['GET'])
def manager_attendance_summary(request):
    """Return per-staff day counts and salary for a month. GET params: month (YYYY-MM) or date (any date in month)."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'results': []})
    month_str = request.GET.get('month')
    date_str = request.GET.get('date')
    if month_str:
        try:
            year, month = int(month_str[:4]), int(month_str[5:7])
        except (ValueError, TypeError):
            return JsonResponse({'results': []})
    elif date_str:
        try:
            d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
            year, month = d.year, d.month
        except ValueError:
            return JsonResponse({'results': []})
    else:
        from django.utils import timezone
        today = timezone.now().date()
        year, month = today.year, today.month
    first = datetime(year, month, 1).date()
    last_day = monthrange(year, month)[1]
    last = datetime(year, month, last_day).date()

    staff_qs = Staff.objects.filter(restaurant_id__in=rid).select_related('user')
    results = []
    for staff in staff_qs:
        att_qs = Attendance.objects.filter(
            restaurant_id__in=rid,
            staff=staff,
            date__gte=first,
            date__lte=last,
        )
        present_days = att_qs.filter(status='present').count()
        leave_days = att_qs.filter(status='leave').count()
        absent_days = att_qs.filter(status='absent').count()
        per_day = staff.per_day_salary or 0
        salary_earned = float(per_day) * present_days if per_day else 0
        name = getattr(staff.user, 'name', None) or getattr(staff.user, 'username', '') or ''
        results.append({
            'staff_id': staff.id,
            'staff_name': name,
            'present_days': present_days,
            'leave_days': leave_days,
            'absent_days': absent_days,
            'per_day_salary': str(per_day),
            'salary_earned': round(salary_earned, 2),
        })
    return JsonResponse({'results': results})
