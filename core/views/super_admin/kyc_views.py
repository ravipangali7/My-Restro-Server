"""Super Admin KYC list (owners), approve/reject. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth import get_user_model

from core.utils import auth_required

User = get_user_model()


def _user_kyc_to_dict(u):
    return {
        'id': u.id,
        'name': getattr(u, 'name', '') or getattr(u, 'username', ''),
        'phone': getattr(u, 'phone', ''),
        'country_code': getattr(u, 'country_code', '') or '',
        'number': getattr(u, 'phone', ''),
        'image': u.image.url if getattr(u, 'image', None) and u.image else None,
        'kyc_status': getattr(u, 'kyc_status', 'pending'),
        'reject_reason': getattr(u, 'reject_reason', '') or '',
        'kyc_document': u.kyc_document.url if getattr(u, 'kyc_document', None) and u.kyc_document else None,
        'created_at': u.created_at.isoformat() if getattr(u, 'created_at', None) else None,
    }


@require_http_methods(['GET'])
def super_admin_kyc_list(request):
    qs = User.objects.filter(is_owner=True).order_by('-date_joined')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(phone__icontains=search) | Q(name__icontains=search))
    total = qs.count()
    pending = qs.filter(kyc_status='pending').count()
    approved = qs.filter(kyc_status='approved').count()
    rejected = qs.filter(kyc_status='rejected').count()
    stats = {'total': total, 'pending': pending, 'approved': approved, 'rejected': rejected}
    results = [_user_kyc_to_dict(u) for u in qs[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_kyc_approve_reject(request, pk):
    u = get_object_or_404(User, pk=pk, is_owner=True)
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        body = {}
    if 'kyc_status' in body:
        u.kyc_status = body['kyc_status']
    if 'reject_reason' in body:
        u.reject_reason = str(body.get('reject_reason', ''))
    u.save()
    return JsonResponse(_user_kyc_to_dict(u))
