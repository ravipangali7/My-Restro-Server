"""Help & Support: read-only list for all staff; CRUD for super_admin."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import HelpSupportEntry
from core.utils import auth_required, super_admin_required


def _entry_to_dict(e):
    return {
        'id': e.id,
        'title': e.title,
        'content': e.content,
        'order': e.order,
        'is_active': e.is_active,
        'created_at': e.created_at.isoformat() if e.created_at else None,
        'updated_at': e.updated_at.isoformat() if e.updated_at else None,
    }


@auth_required
@require_http_methods(['GET'])
def help_support_list(request):
    """GET /api/auth/help-support/ - active entries for all staff (ordered)."""
    qs = HelpSupportEntry.objects.filter(is_active=True).order_by('order', 'id')
    results = [_entry_to_dict(e) for e in qs]
    return JsonResponse({'results': results})


@super_admin_required
@require_http_methods(['GET'])
def super_admin_help_support_list(request):
    """GET /api/super_admin/help-support/ - all entries for super_admin."""
    qs = HelpSupportEntry.objects.all().order_by('order', 'id')
    results = [_entry_to_dict(e) for e in qs]
    return JsonResponse({'results': results})


@csrf_exempt
@super_admin_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_help_support_update(request, pk):
    """PATCH /api/super_admin/help-support/<id>/ - update entry."""
    entry = get_object_or_404(HelpSupportEntry, pk=pk)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'title' in body:
        entry.title = str(body['title']).strip() or entry.title
    if 'content' in body:
        entry.content = str(body['content'])
    if 'order' in body:
        try:
            entry.order = int(body['order'])
        except (TypeError, ValueError):
            pass
    if 'is_active' in body:
        entry.is_active = str(body['is_active']).lower() in ('true', '1', 'yes')
    entry.save()
    return JsonResponse(_entry_to_dict(entry))


@csrf_exempt
@super_admin_required
@require_http_methods(['POST'])
def super_admin_help_support_create(request):
    """POST /api/super_admin/help-support/create/ - create entry."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    title = str(body.get('title') or '').strip()
    if not title:
        return JsonResponse({'error': 'title required'}, status=400)
    content = str(body.get('content') or '')
    order = 0
    if 'order' in body:
        try:
            order = int(body['order'])
        except (TypeError, ValueError):
            pass
    is_active = str(body.get('is_active', True)).lower() in ('true', '1', 'yes')
    entry = HelpSupportEntry.objects.create(
        title=title,
        content=content,
        order=order,
        is_active=is_active,
    )
    return JsonResponse(_entry_to_dict(entry), status=201)
