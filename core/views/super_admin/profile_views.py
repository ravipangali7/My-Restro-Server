"""Super Admin profile listing and edit by id. Returns users (staff + owners) with role and status."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Q

from core.models import User
from core.utils import auth_required, get_role
from core.constants import ALLOWED_COUNTRY_CODES


def _require_super_admin(request):
    if not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Super admin required'}, status=403)
    return None


def _profile_to_dict(u):
    """Return dict with image, name, country_code, phone, role, status for listing."""
    return {
        'id': u.id,
        'image': u.image.url if getattr(u, 'image', None) and u.image else None,
        'name': getattr(u, 'name', '') or getattr(u, 'username', '') or '',
        'country_code': getattr(u, 'country_code', '') or '',
        'phone': getattr(u, 'phone', '') or '',
        'role': get_role(u) or 'owner',
        'status': 'active' if getattr(u, 'is_active', True) else 'inactive',
    }


def _profile_detail_to_dict(u):
    """Full profile for GET detail and PATCH response."""
    d = _profile_to_dict(u)
    d['email'] = getattr(u, 'email', '') or ''
    d['is_active'] = getattr(u, 'is_active', True)
    return d


def _get_request_body(request):
    """Parse body from PATCH form or JSON. Returns (dict, image_file)."""
    if request.POST or request.FILES:
        body = dict(request.POST.items()) if request.POST else {}
        for k, v in body.items():
            if isinstance(v, list) and len(v) == 1:
                body[k] = v[0]
        return body, request.FILES.get('image') if request.FILES else None
    content_type = (request.META.get('CONTENT_TYPE') or '').lower()
    if 'application/json' in content_type and request.body:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = {}
    else:
        body = {}
    return body, None


@auth_required
@require_http_methods(['GET'])
def super_admin_profile_list(request):
    """GET /api/super_admin/profiles/ - list users (superuser, owners, restaurant staff) with role and status."""
    err = _require_super_admin(request)
    if err:
        return err
    # Users who are staff: superuser, owner, or restaurant_staff (manager/waiter)
    qs = User.objects.filter(
        Q(is_superuser=True) | Q(is_owner=True) | Q(is_restaurant_staff=True)
    ).order_by('-date_joined')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(phone__icontains=search) | Q(name__icontains=search) | Q(email__icontains=search)
        )
    role_filter = request.GET.get('role', '').strip()
    if role_filter:
        # Filter by role: need to annotate or filter in Python (get_role is not a DB field)
        results = []
        for u in qs[:200]:
            r = get_role(u)
            if r == role_filter:
                results.append(_profile_to_dict(u))
        return JsonResponse({'results': results})
    results = [_profile_to_dict(u) for u in qs[:100]]
    return JsonResponse({'results': results})


@auth_required
@require_http_methods(['GET'])
def super_admin_profile_detail(request, pk):
    """GET /api/super_admin/profiles/<id>/ - detail for edit."""
    err = _require_super_admin(request)
    if err:
        return err
    u = get_object_or_404(User, pk=pk)
    # Only allow viewing staff/owner profiles (same set as list)
    if not (u.is_superuser or u.is_owner or u.is_restaurant_staff):
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(_profile_detail_to_dict(u))


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_profile_update(request, pk):
    """PATCH /api/super_admin/profiles/<id>/ - update name, country_code, phone, image."""
    err = _require_super_admin(request)
    if err:
        return err
    u = get_object_or_404(User, pk=pk)
    if not (u.is_superuser or u.is_owner or u.is_restaurant_staff):
        return JsonResponse({'error': 'Not found'}, status=404)
    body, image_file = _get_request_body(request)
    if image_file:
        u.image = image_file
    if 'name' in body:
        u.name = str(body['name']).strip()
    if 'phone' in body:
        new_phone = str(body['phone']).strip()
        if new_phone and User.objects.filter(phone=new_phone).exclude(pk=u.pk).exists():
            return JsonResponse({'error': 'Another user with this phone already exists'}, status=400)
        u.phone = new_phone
    if 'country_code' in body:
        new_cc = str(body['country_code']).strip()
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
            }, status=400)
        u.country_code = new_cc
    u.save()
    return JsonResponse(_profile_detail_to_dict(u))
