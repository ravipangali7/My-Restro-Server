"""Manager attendance list by date, set present/absent/leave, summary with salary. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from datetime import datetime
from calendar import monthrange

from core.models import Attendance, Staff, SalaryType
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


def _calc_staff_salary(staff, present_days):
    """Calculate earned salary for a staff in a month based on salary_type."""
    salary_type = getattr(staff, 'salary_type', None) or SalaryType.PER_DAY
    if salary_type == SalaryType.MONTHLY:
        return float(staff.salary or 0)
    per_day = float(staff.per_day_salary or 0)
    return round(per_day * present_days, 2)


@require_http_methods(['GET'])
def manager_attendance_list(request):
    """List attendance with optional filters: date, date_from, date_to, month, staff_id. Stats include total_staff."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'stats': {}, 'results': []})
    qs = Attendance.objects.filter(restaurant_id__in=rid).select_related('staff__user')

    date = request.GET.get('date')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    month_str = request.GET.get('month')
    staff_id = request.GET.get('staff_id')

    if staff_id:
        try:
            qs = qs.filter(staff_id=int(staff_id))
        except ValueError:
            pass

    if date:
        try:
            d = datetime.strptime(date[:10], '%Y-%m-%d').date()
            qs = qs.filter(date=d)
        except ValueError:
            pass
    elif date_from and date_to:
        try:
            df = datetime.strptime(date_from[:10], '%Y-%m-%d').date()
            dt = datetime.strptime(date_to[:10], '%Y-%m-%d').date()
            qs = qs.filter(date__gte=df, date__lte=dt)
        except ValueError:
            pass
    elif month_str:
        try:
            year, month = int(month_str[:4]), int(month_str[5:7])
            first = datetime(year, month, 1).date()
            last_day = monthrange(year, month)[1]
            last = datetime(year, month, last_day).date()
            qs = qs.filter(date__gte=first, date__lte=last)
        except (ValueError, TypeError, IndexError):
            pass

    total_staff = Staff.objects.filter(restaurant_id__in=rid).count()
    present = qs.filter(status='present').count()
    absent = qs.filter(status='absent').count()
    leave = qs.filter(status='leave').count()
    stats = {
        'total_staff': total_staff,
        'present': present,
        'absent': absent,
        'leave': leave,
        'present_today': present,
        'absent_today': absent,
        'on_leave_today': leave,
    }
    results = [_attendance_to_dict(a) for a in qs.order_by('-date', 'staff__user__name')[:200]]
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
    att, created = Attendance.objects.get_or_create(
        restaurant=staff.restaurant,
        staff=staff,
        date=d,
        defaults={'status': status, 'leave_reason': body.get('leave_reason', ''), 'created_by': request.user}
    )
    if not created:
        att.status = status
        att.leave_reason = body.get('leave_reason', '')
        att.created_by = request.user
        att.save()
    return JsonResponse(_attendance_to_dict(att))


@auth_required
@require_http_methods(['GET'])
def manager_attendance_summary(request):
    """Return per-staff day counts and calculated salary for a month. GET params: month (YYYY-MM), date, staff_id."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'results': [], 'stats': {}})
    month_str = request.GET.get('month')
    date_str = request.GET.get('date')
    staff_id_param = request.GET.get('staff_id')

    if month_str:
        try:
            year, month = int(month_str[:4]), int(month_str[5:7])
        except (ValueError, TypeError, IndexError):
            return JsonResponse({'results': [], 'stats': {}})
    elif date_str:
        try:
            d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
            year, month = d.year, d.month
        except ValueError:
            return JsonResponse({'results': [], 'stats': {}})
    else:
        from django.utils import timezone
        today = timezone.now().date()
        year, month = today.year, today.month
    first = datetime(year, month, 1).date()
    last_day = monthrange(year, month)[1]
    last = datetime(year, month, last_day).date()

    staff_qs = Staff.objects.filter(restaurant_id__in=rid).select_related('user')
    if staff_id_param:
        try:
            staff_qs = staff_qs.filter(pk=int(staff_id_param))
        except ValueError:
            pass

    total_monthly_salary_calc = 0
    total_per_day_salary_calc = 0
    total_payable_salary = 0
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
        salary_type = getattr(staff, 'salary_type', None) or SalaryType.PER_DAY
        calculated_salary = _calc_staff_salary(staff, present_days)
        monthly_salary = float(staff.salary or 0)
        per_day_salary = float(staff.per_day_salary or 0)
        if salary_type == SalaryType.MONTHLY:
            total_monthly_salary_calc += calculated_salary
        else:
            total_per_day_salary_calc += calculated_salary
        total_payable_salary += calculated_salary
        name = getattr(staff.user, 'name', None) or getattr(staff.user, 'username', '') or ''
        results.append({
            'staff_id': staff.id,
            'staff_name': name,
            'present_days': present_days,
            'leave_days': leave_days,
            'absent_days': absent_days,
            'salary_type': salary_type,
            'per_day_salary': str(per_day_salary),
            'monthly_salary': str(monthly_salary),
            'calculated_salary': calculated_salary,
            'salary_earned': calculated_salary,
        })
    stats = {
        'total_monthly_salary_calc': round(total_monthly_salary_calc, 2),
        'total_per_day_salary_calc': round(total_per_day_salary_calc, 2),
        'total_payable_salary': round(total_payable_salary, 2),
    }
    return JsonResponse({'results': results, 'stats': stats})


@auth_required
@require_http_methods(['DELETE'])
def manager_attendance_delete(request, id):
    """Delete a single attendance record. Manager only; restaurant must match."""
    rid = get_restaurant_ids(request)
    if not rid:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    att = get_object_or_404(Attendance, pk=id, restaurant_id__in=rid)
    att.delete()
    return JsonResponse({'ok': True}, status=200)
