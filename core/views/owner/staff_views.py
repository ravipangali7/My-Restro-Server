"""Owner staff list, create, update, delete. Function-based."""
import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from django.db.models import Count, Sum, Avg
from core.models import Staff, Restaurant, Table, Order, Feedback, PaidRecord
from core.utils import get_restaurant_ids, auth_required, image_url_for_request
from core.permissions import is_manager
from core.constants import ALLOWED_COUNTRY_CODES

User = get_user_model()


def _decimal_or_none(val):
    """Return Decimal(val) if val is present and valid, else None. Reject negative."""
    if val is None or val == '':
        return None
    try:
        d = Decimal(str(val))
        if d < 0:
            return None  # caller checks and returns 400
        return d
    except (InvalidOperation, TypeError, ValueError):
        return None


def _staff_to_dict(s, request=None):
    name = getattr(s.user, 'name', None) or (getattr(s.user, 'username', '')) or ''
    joined_at = s.joined_at
    if joined_at is None:
        joined_at_str = None
    elif hasattr(joined_at, 'isoformat'):
        joined_at_str = joined_at.isoformat()
    else:
        joined_at_str = str(joined_at)[:10] if joined_at else None
    assigned_table_ids = list(s.assigned_tables.values_list('id', flat=True))
    user_image = image_url_for_request(request, getattr(s.user, 'image', None))
    return {
        'id': s.id,
        'restaurant_id': s.restaurant_id,
        'user_id': s.user_id,
        'user_name': name,
        'name': name,
        'user_phone': getattr(s.user, 'phone', ''),
        'image': user_image,
        'is_manager': s.is_manager,
        'is_waiter': s.is_waiter,
        'is_kitchen': getattr(s.user, 'is_kitchen', False),
        'designation': s.designation or '',
        'joined_at': joined_at_str,
        'salary': str(s.salary) if s.salary is not None else None,
        'per_day_salary': str(s.per_day_salary) if s.per_day_salary is not None else None,
        'is_suspend': s.is_suspend,
        'to_pay': str(s.to_pay),
        'to_receive': str(s.to_receive),
        'assigned_table_ids': assigned_table_ids,
        'created_at': s.created_at.isoformat() if s.created_at else None,
        'updated_at': s.updated_at.isoformat() if s.updated_at else None,
    }


def _staff_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Staff.objects.all()
    elif rid:
        qs = Staff.objects.filter(restaurant_id__in=rid)
    else:
        qs = Staff.objects.none()
    return qs.select_related('user').prefetch_related('assigned_tables')


def _user_to_dict(u, request=None):
    """Return minimal user payload for check/create responses."""
    image_url = image_url_for_request(request, getattr(u, 'image', None))
    return {
        'id': u.id,
        'name': getattr(u, 'name', None) or getattr(u, 'username', '') or str(u.id),
        'phone': getattr(u, 'phone', '') or '',
        'image': image_url,
    }


@auth_required
@require_http_methods(['GET'])
def owner_user_check(request):
    """Check if a user exists by numeric id or phone. Returns 200 + { id, name, phone } or 404."""
    id_or_phone = (request.GET.get('id') or request.GET.get('phone') or '').strip()
    if not id_or_phone:
        return JsonResponse({'error': 'id or phone required'}, status=400)
    user = None
    if id_or_phone.isdigit():
        user = User.objects.filter(pk=int(id_or_phone), is_active=True).first()
    if user is None:
        user = User.objects.filter(phone=id_or_phone, is_active=True).first()
    if user is None:
        return JsonResponse({'error': 'User not found'}, status=404)
    return JsonResponse(_user_to_dict(user, request))


@auth_required
@require_http_methods(['GET'])
def owner_available_users(request):
    """List users available for staff assignment (id, name, phone)."""
    qs = User.objects.filter(is_active=True).order_by('name')
    results = [_user_to_dict(u, request) for u in qs]
    return JsonResponse({'results': results})


def _owner_can_update_user(request, target_user):
    """True if owner can update target_user (e.g. for image). User must be staff in owner's restaurants or not staff in any (available to assign)."""
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return False
    if getattr(request.user, 'is_superuser', False):
        return True
    # Staff in one of owner's restaurants
    if Staff.objects.filter(restaurant_id__in=rid, user=target_user).exists():
        return True
    # Not staff in any of owner's restaurants (available for assignment)
    if not Staff.objects.filter(restaurant_id__in=rid, user=target_user).exists():
        return True
    return False


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_user_update(request, user_id):
    """PATCH /owner/users/<user_id>/update/ - update user image (multipart). Owner can update users that are staff or available for staff."""
    target = get_object_or_404(User, pk=user_id)
    if not target.is_active:
        return JsonResponse({'error': 'User not found or inactive'}, status=404)
    if not _owner_can_update_user(request, target):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image') if request.FILES else None
    if image_file:
        target.image = image_file
        target.save(update_fields=['image'])
    return JsonResponse(_user_to_dict(target, request))


def _parse_user_create_request(request):
    """Parse body from POST form + FILES or JSON. Returns (body_dict, image_file)."""
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


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_user_create(request):
    """Create a non-owner user for staff assignment. Accepts phone, country_code (required), password, name (optional), image (optional multipart)."""
    body, image_file = _parse_user_create_request(request)
    phone = (body.get('phone') or '').strip()
    country_code = (body.get('country_code') or '').strip()
    password = body.get('password', '')
    if not phone:
        return JsonResponse({'error': 'phone required'}, status=400)
    if not country_code:
        return JsonResponse({'error': 'Country code is required.'}, status=400)
    if country_code not in ALLOWED_COUNTRY_CODES:
        return JsonResponse({
            'error': 'Invalid country code. Only +91 (India) and +977 (Nepal) are allowed.'
        }, status=400)
    if not password:
        return JsonResponse({'error': 'password required'}, status=400)
    if User.objects.filter(country_code=country_code, phone=phone).exists():
        return JsonResponse({'error': 'User with this country code and phone already exists'}, status=400)
    try:
        validate_password(password)
    except ValidationError as e:
        msg = (list(e.messages)[0] if e.messages else None) or 'Invalid password'
        return JsonResponse({'error': msg}, status=400)
    name = (body.get('name') or '').strip()
    username = f'{country_code}_{phone}'
    if User.objects.filter(username=username).exists():
        username = f"staff_{country_code}_{phone}_{User.objects.count()}"
    user = User.objects.create_user(username=username, password=password, email=username)
    user.phone = phone
    user.country_code = country_code
    user.name = name or username
    user.is_owner = False
    user.is_restaurant_staff = True
    user.is_active = True
    if image_file:
        user.image = image_file
    user.save()
    return JsonResponse(_user_to_dict(user, request), status=201)


@auth_required
@require_http_methods(['GET'])
def owner_staff_list(request):
    qs = _staff_qs(request)
    active = qs.filter(is_suspend=False)
    inactive = qs.filter(is_suspend=True)
    stats = {'total': qs.count(), 'active': active.count(), 'inactive': inactive.count()}
    staff_list = list(qs.order_by('user__name'))
    staff_ids = [s.id for s in staff_list]
    orders_handled_map = {}
    feedback_avg_map = {}
    total_paid_map = {}
    if staff_ids:
        orders_handled_map = dict(
            Order.objects.filter(waiter_id__in=staff_ids)
            .values('waiter_id')
            .annotate(c=Count('id'))
            .values_list('waiter_id', 'c')
        )
        feedback_avg_map = dict(
            Feedback.objects.filter(staff_id__in=staff_ids)
            .values('staff_id')
            .annotate(avg=Avg('rating'))
            .values_list('staff_id', 'avg')
        )
        total_paid_map = dict(
            PaidRecord.objects.filter(staff_id__in=staff_ids)
            .values('staff_id')
            .annotate(total=Sum('amount'))
            .values_list('staff_id', 'total')
        )
    results = []
    for s in staff_list:
        d = _staff_to_dict(s, request)
        d['orders_handled'] = orders_handled_map.get(s.id, 0)
        avg_rating = feedback_avg_map.get(s.id)
        d['feedback_rating_avg'] = round(float(avg_rating), 1) if avg_rating is not None else None
        total_paid = total_paid_map.get(s.id)
        d['total_paid'] = str(total_paid) if total_paid is not None else '0'
        results.append(d)
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
def owner_staff_list_or_create(request):
    """GET -> list, POST -> create (so POST /owner/staff/ works)."""
    if request.method == 'GET':
        return owner_staff_list(request)
    return owner_staff_create(request)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_staff_create(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    rid = get_restaurant_ids(request)
    restaurant_id = body.get('restaurant_id')
    if not restaurant_id:
        return JsonResponse({'error': 'restaurant_id required'}, status=400)
    if rid and int(restaurant_id) not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    restaurant = get_object_or_404(Restaurant, pk=restaurant_id)
    user_id = body.get('user_id')
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=400)
    if Staff.objects.filter(restaurant=restaurant, user=user).exists():
        return JsonResponse({'error': 'This user is already staff in this restaurant.'}, status=400)
    is_manager = bool(body.get('is_manager', False))
    is_waiter = bool(body.get('is_waiter', False))
    is_kitchen = bool(body.get('is_kitchen', False))
    if not (is_manager or is_waiter or is_kitchen):
        return JsonResponse(
            {'error': 'At least one role (Manager, Waiter, or Kitchen) must be selected.'},
            status=400,
        )
    salary_val = body.get('salary')
    per_day_val = body.get('per_day_salary')
    salary = _decimal_or_none(salary_val)
    per_day_salary = _decimal_or_none(per_day_val)
    if salary_val is not None and salary_val != '' and salary is None:
        return JsonResponse({'error': 'Invalid or negative salary'}, status=400)
    if per_day_val is not None and per_day_val != '' and per_day_salary is None:
        return JsonResponse({'error': 'Invalid or negative per_day_salary'}, status=400)
    password = body.get('password')
    if password is not None and password != '':
        try:
            validate_password(password, user)
        except ValidationError as e:
            msg = (list(e.messages)[0] if e.messages else None) or 'Invalid password'
            return JsonResponse({'error': msg}, status=400)
        user.set_password(password)
        user.save()
    s = Staff(
        restaurant=restaurant,
        user=user,
        is_manager=is_manager,
        is_waiter=is_waiter,
        designation=body.get('designation', ''),
        joined_at=body.get('joined_at'),
        salary=salary,
        per_day_salary=per_day_salary,
        is_suspend=bool(body.get('is_suspend', False)),
    )
    try:
        s.save()
    except IntegrityError:
        return JsonResponse({'error': 'This user is already staff in this restaurant.'}, status=400)
    # Set User.is_restaurant_staff and User.is_kitchen for kitchen dashboard access
    user.is_restaurant_staff = True
    user.is_kitchen = is_kitchen
    user.save(update_fields=['is_restaurant_staff', 'is_kitchen'])
    if s.is_waiter and 'assigned_table_ids' in body:
        raw_ids = body['assigned_table_ids']
        if isinstance(raw_ids, list):
            table_ids = []
            for x in raw_ids:
                if x is None or str(x).strip() == '':
                    continue
                try:
                    table_ids.append(int(x))
                except (TypeError, ValueError):
                    continue
            table_objs = list(Table.objects.filter(pk__in=table_ids, restaurant_id=s.restaurant_id))
            s.assigned_tables.set(table_objs)
    return JsonResponse(_staff_to_dict(s, request), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_staff_update(request, pk):
    s = get_object_or_404(Staff, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and s.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    # Manager cannot grant manager role to a user who is Owner (role change to Owner is restricted)
    if is_manager(request.user) and not getattr(request.user, 'is_superuser', False):
        if body.get('is_manager') is True and getattr(s.user, 'is_owner', False):
            return JsonResponse({'error': 'Cannot change role for Owner'}, status=403)
    if 'is_manager' in body:
        s.is_manager = bool(body['is_manager'])
    if 'is_waiter' in body:
        s.is_waiter = bool(body['is_waiter'])
    if 'is_kitchen' in body:
        s.user.is_kitchen = bool(body['is_kitchen'])
        s.user.save(update_fields=['is_kitchen'])
    if 'designation' in body:
        s.designation = str(body.get('designation', ''))
    if 'joined_at' in body:
        s.joined_at = body['joined_at'] or None
    if 'salary' in body:
        salary = _decimal_or_none(body['salary'])
        if body['salary'] is not None and body['salary'] != '' and salary is None:
            return JsonResponse({'error': 'Invalid or negative salary'}, status=400)
        s.salary = salary
    if 'per_day_salary' in body:
        per_day = _decimal_or_none(body['per_day_salary'])
        if body['per_day_salary'] is not None and body['per_day_salary'] != '' and per_day is None:
            return JsonResponse({'error': 'Invalid or negative per_day_salary'}, status=400)
        s.per_day_salary = per_day
    if 'is_suspend' in body:
        s.is_suspend = bool(body['is_suspend'])
    if 'assigned_table_ids' in body:
        raw_ids = body['assigned_table_ids']
        if not isinstance(raw_ids, list):
            raw_ids = []
        table_ids = []
        for x in raw_ids:
            if x is None or str(x).strip() == '':
                continue
            try:
                table_ids.append(int(x))
            except (TypeError, ValueError):
                continue
        table_objs = list(Table.objects.filter(pk__in=table_ids, restaurant_id=s.restaurant_id))
        s.assigned_tables.set(table_objs)
    password = body.get('password')
    if password is not None and password != '':
        try:
            validate_password(password, s.user)
        except ValidationError as e:
            msg = (list(e.messages)[0] if e.messages else None) or 'Invalid password'
            return JsonResponse({'error': msg}, status=400)
        s.user.set_password(password)
        s.user.save()
    if not (s.is_manager or s.is_waiter or getattr(s.user, 'is_kitchen', False)):
        return JsonResponse(
            {'error': 'At least one role (Manager, Waiter, or Kitchen) must be selected.'},
            status=400,
        )
    s.save()
    return JsonResponse(_staff_to_dict(s, request))


@csrf_exempt
@auth_required
@require_http_methods(['DELETE'])
def owner_staff_delete(request, pk):
    s = get_object_or_404(Staff, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and s.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    s.delete()
    return JsonResponse({'success': True}, status=200)
