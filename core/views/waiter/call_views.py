"""Waiter: list and update WaiterCall (calls assigned to this waiter)."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import WaiterCall, WaiterCallStatus
from core.utils import get_waiter_staff_id


def _call_to_dict(c):
    return {
        'id': c.id,
        'restaurant_id': c.restaurant_id,
        'table_id': c.table_id,
        'table_number': c.table_number or '',
        'customer_name': c.customer_name or '',
        'message': c.message or '',
        'status': c.status,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'updated_at': c.updated_at.isoformat() if c.updated_at else None,
    }


@require_http_methods(['GET'])
def waiter_call_list(request):
    """GET /api/waiter/calls/ — list calls assigned to current waiter; includes pending_count."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'results': [], 'pending_count': 0})
    qs = WaiterCall.objects.filter(assigned_to_id=staff_id).select_related(
        'restaurant', 'table'
    ).order_by('-created_at')
    pending_count = qs.filter(status=WaiterCallStatus.PENDING).count()
    results = [_call_to_dict(c) for c in qs]
    return JsonResponse({'results': results, 'pending_count': pending_count})


@require_http_methods(['GET'])
def waiter_call_pending_count(request):
    """GET /api/waiter/calls/pending-count/ — only pending count for badge."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'count': 0})
    count = WaiterCall.objects.filter(
        assigned_to_id=staff_id, status=WaiterCallStatus.PENDING
    ).count()
    return JsonResponse({'count': count})


@csrf_exempt
@require_http_methods(['PATCH', 'PUT'])
def waiter_call_update(request, pk):
    """PATCH /api/waiter/calls/<id>/ — waiter can set status=completed (only own calls)."""
    staff_id = get_waiter_staff_id(request)
    if not staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    call = get_object_or_404(WaiterCall, pk=pk)
    if call.assigned_to_id != staff_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if body.get('status') == WaiterCallStatus.COMPLETED:
        call.status = WaiterCallStatus.COMPLETED
        call.save(update_fields=['status', 'updated_at'])
    return JsonResponse(_call_to_dict(call))
