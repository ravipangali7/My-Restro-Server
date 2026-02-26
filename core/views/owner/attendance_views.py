"""Owner attendance summary (read-only): per-staff counts and trend for charts."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from core.models import Attendance, Staff
from core.utils import get_restaurant_ids, auth_required


@auth_required
@require_http_methods(['GET'])
def owner_attendance_summary(request):
    """GET /owner/attendance/summary/ - per-staff present/absent/leave (last 30 days) and daily trend (last 14 days)."""
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({
            'summary': [],
            'trend': [],
        })

    today = timezone.now().date()
    start_30 = today - timedelta(days=30)
    start_14 = today - timedelta(days=14)

    # Per-staff summary (last 30 days)
    att_qs = (
        Attendance.objects.filter(restaurant_id__in=rid, date__gte=start_30)
        .values('staff_id')
        .annotate(
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            leave=Count('id', filter=Q(status='leave')),
        )
    )
    staff_ids = [row['staff_id'] for row in att_qs if row['staff_id']]
    staff_by_id = {}
    if staff_ids:
        for s in Staff.objects.filter(id__in=staff_ids).select_related('user'):
            staff_by_id[s.id] = getattr(s.user, 'name', '') or getattr(s.user, 'username', '') or f'Staff {s.id}'
    summary = []
    for row in att_qs:
        summary.append({
            'staff_id': row['staff_id'],
            'staff_name': staff_by_id.get(row['staff_id'], '—'),
            'present': row['present'],
            'absent': row['absent'],
            'leave': row['leave'],
        })

    # Daily trend (last 14 days) for chart
    trend = []
    for i in range(14):
        d = start_14 + timedelta(days=i)
        day_qs = Attendance.objects.filter(restaurant_id__in=rid, date=d)
        trend.append({
            'date': d.isoformat(),
            'name': d.strftime('%m/%d'),
            'present': day_qs.filter(status='present').count(),
            'absent': day_qs.filter(status='absent').count(),
            'leave': day_qs.filter(status='leave').count(),
        })

    return JsonResponse({
        'summary': summary,
        'trend': trend,
    })
