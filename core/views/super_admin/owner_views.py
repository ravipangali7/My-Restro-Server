"""Super Admin owners (User with is_owner=True) list, create, update, delete. Function-based."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from decimal import Decimal
from django.db.models import Q, Count, Sum

from core.models import User, Restaurant, Order, OrderStatus
from core.utils import auth_required
from core.constants import ALLOWED_COUNTRY_CODES


def _require_super_admin(request):
    if not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Super admin required'}, status=403)
    return None


def _get_request_body(request):
    """Parse body from POST form or JSON. Returns (dict, image_file). Never reads request.body for multipart (avoids UnicodeDecodeError on binary)."""
    # Always prefer POST + FILES when present (multipart or form-urlencoded). Do not touch request.body.
    if request.POST or request.FILES:
        body = dict(request.POST.items()) if request.POST else {}
        for k, v in body.items():
            if isinstance(v, list) and len(v) == 1:
                body[k] = v[0]
        return body, request.FILES.get('image') if request.FILES else None
    # JSON body only when no POST/FILES (e.g. create without image)
    content_type = (request.META.get('CONTENT_TYPE') or getattr(request, 'content_type', None) or '').lower()
    if 'application/json' in content_type and request.body:
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            body = {}
    else:
        body = {}
    return body, None


def _owner_to_dict(u):
    return {
        'id': u.id,
        'name': getattr(u, 'name', '') or getattr(u, 'username', ''),
        'phone': getattr(u, 'phone', ''),
        'country_code': getattr(u, 'country_code', '') or '',
        'email': getattr(u, 'email', '') or '',
        'first_name': getattr(u, 'first_name', '') or '',
        'last_name': getattr(u, 'last_name', '') or '',
        'is_active': getattr(u, 'is_active', True),
        'kyc_status': getattr(u, 'kyc_status', 'pending'),
        'reject_reason': getattr(u, 'reject_reason', '') or '',
        'kyc_document': u.kyc_document.url if getattr(u, 'kyc_document', None) and u.kyc_document else None,
        'image': u.image.url if getattr(u, 'image', None) and u.image else None,
        'created_at': u.created_at.isoformat() if getattr(u, 'created_at', None) else None,
        'restaurant_count': u.restaurants.count() if hasattr(u, 'restaurants') else 0,
    }


@auth_required
@require_http_methods(['GET'])
def super_admin_owner_list(request):
    err = _require_super_admin(request)
    if err:
        return err
    qs = User.objects.filter(is_owner=True).annotate(
        restaurant_count=Count('restaurants')
    ).order_by('-date_joined')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(phone__icontains=search) | Q(name__icontains=search) | Q(email__icontains=search)
        )
    total = qs.count()
    pending = qs.filter(kyc_status='pending').count()
    approved = qs.filter(kyc_status='approved').count()
    rejected = qs.filter(kyc_status='rejected').count()
    stats = {'total': total, 'pending': pending, 'approved': approved, 'rejected': rejected}
    results = []
    for u in qs[:100]:
        d = _owner_to_dict(u)
        d['restaurant_count'] = u.restaurant_count
        results.append(d)
    return JsonResponse({'stats': stats, 'results': results})


@auth_required
@require_http_methods(['GET'])
def super_admin_owner_detail(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    u = get_object_or_404(User, pk=pk, is_owner=True)
    data = _owner_to_dict(u)
    restaurants_qs = Restaurant.objects.filter(user=u)
    restaurant_count = restaurants_qs.count()
    total_revenue = Decimal('0')
    total_due = Decimal('0')
    total_orders = 0
    restaurants = []
    revenue_by_restaurant = []
    for r in restaurants_qs:
        rev = Order.objects.filter(restaurant=r).exclude(status=OrderStatus.REJECTED).aggregate(s=Sum('total'))['s'] or Decimal('0')
        order_count = Order.objects.filter(restaurant=r).count()
        total_revenue += rev
        total_due += r.due_balance or Decimal('0')
        total_orders += order_count
        restaurants.append({
            'id': r.id,
            'name': r.name,
            'slug': r.slug or '',
            'balance': str(r.balance),
            'due_balance': str(r.due_balance),
            'revenue': str(rev),
            'order_count': order_count,
            'is_open': r.is_open,
            'subscription_end': r.subscription_end.isoformat() if r.subscription_end else None,
        })
        revenue_by_restaurant.append({
            'restaurant_id': r.id,
            'restaurant_name': r.name,
            'revenue': float(rev),
        })
    data['stats'] = {
        'restaurant_count': restaurant_count,
        'total_revenue': str(total_revenue),
        'total_due': str(total_due),
        'pending_kyc': 1 if getattr(u, 'kyc_status', None) == 'pending' else 0,
        'order_count': total_orders,
    }
    data['restaurants'] = restaurants
    data['revenue_by_restaurant'] = revenue_by_restaurant
    return JsonResponse(data)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def super_admin_owner_create(request):
    err = _require_super_admin(request)
    if err:
        return err
    body, image_file = _get_request_body(request)
    phone = (body.get('phone') or '').strip()
    password = body.get('password', '')
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not password:
        return JsonResponse({'error': 'password required'}, status=400)
    if User.objects.filter(phone=phone).exists():
        return JsonResponse({'error': 'User with this phone already exists'}, status=400)
    name = (body.get('name') or '').strip()
    country_code = (body.get('country_code') or '').strip()
    if country_code and country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
        }, status=400)
    email = (body.get('email') or '').strip()
    first_name = (body.get('first_name') or '').strip()
    last_name = (body.get('last_name') or '').strip()
    username = phone if not country_code else f"{country_code}{phone}"
    if User.objects.filter(username=username).exists():
        username = f"owner_{phone}_{User.objects.count()}"
    user = User.objects.create_user(
        username=username,
        password=password,
        email=email or username,
    )
    user.phone = phone
    user.name = name or (f"{first_name} {last_name}".strip() or username)
    user.country_code = country_code
    user.first_name = first_name
    user.last_name = last_name
    user.is_owner = True
    user.kyc_status = body.get('kyc_status', 'pending')
    user.is_active = str(body.get('is_active', True)).lower() in ('true', '1', 'yes')
    if image_file:
        user.image = image_file
    user.save()
    return JsonResponse(_owner_to_dict(user), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PATCH', 'PUT'])
def super_admin_owner_update(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    u = get_object_or_404(User, pk=pk, is_owner=True)
    body, image_file = _get_request_body(request)
    if image_file:
        u.image = image_file
    if 'name' in body:
        u.name = str(body['name']).strip()
    if 'phone' in body:
        u.phone = str(body['phone']).strip()
    if 'country_code' in body:
        new_cc = str(body['country_code']).strip()
        if new_cc and new_cc not in ALLOWED_COUNTRY_CODES:
            return JsonResponse({
                'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
            }, status=400)
        u.country_code = new_cc
    if 'email' in body:
        u.email = str(body['email']).strip()
    if 'first_name' in body:
        u.first_name = str(body['first_name']).strip()
    if 'last_name' in body:
        u.last_name = str(body['last_name']).strip()
    if 'is_active' in body:
        u.is_active = str(body['is_active']).lower() in ('true', '1', 'yes')
    if 'kyc_status' in body:
        u.kyc_status = str(body['kyc_status'])
    if 'reject_reason' in body:
        u.reject_reason = str(body.get('reject_reason', ''))
    if body.get('password'):
        u.set_password(body['password'])
    u.save()
    return JsonResponse(_owner_to_dict(u))


@csrf_exempt
@auth_required
@require_http_methods(['DELETE'])
def super_admin_owner_delete(request, pk):
    err = _require_super_admin(request)
    if err:
        return err
    u = get_object_or_404(User, pk=pk, is_owner=True)
    if u.restaurants.exists():
        return JsonResponse(
            {'error': 'Cannot delete owner with restaurants. Deactivate instead.'},
            status=400
        )
    u.delete()
    return JsonResponse({'success': True})
