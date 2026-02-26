"""In-app notification list, create, and recipients. Shared logic for staff and customer auth."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from core.models import (
    InAppNotification,
    User,
    Customer,
    Staff,
    Restaurant,
    CustomerRestaurant,
    Order,
)
from core.utils import (
    get_restaurant_ids,
    get_customer_id_from_request,
    get_role,
    auth_required,
    customer_auth_required,
)


def _notification_to_dict(n):
    sender_name = getattr(n.sender, 'name', None) or getattr(n.sender, 'username', '') or '—'
    if n.recipient_user_id:
        recipient_type = 'staff'
        recipient_id = n.recipient_user_id
        recipient_name = getattr(n.recipient_user, 'name', None) or getattr(n.recipient_user, 'username', '') or '—'
    else:
        recipient_type = 'customer'
        recipient_id = n.recipient_customer_id
        recipient_name = getattr(n.recipient_customer, 'name', '—') if n.recipient_customer else '—'
    return {
        'id': n.id,
        'sender_id': n.sender_id,
        'sender_name': sender_name,
        'recipient_type': recipient_type,
        'recipient_id': recipient_id,
        'recipient_name': recipient_name,
        'purpose': n.purpose or '',
        'created_at': n.created_at.isoformat() if n.created_at else None,
        'read_at': n.read_at.isoformat() if n.read_at else None,
    }


# --- List (staff: auth_required; customer: customer_auth_required) ---

@auth_required
@require_http_methods(['GET'])
def in_app_notification_list_staff(request):
    """List in-app notifications where current user is recipient (staff)."""
    qs = InAppNotification.objects.filter(recipient_user=request.user).select_related(
        'sender', 'recipient_user', 'recipient_customer'
    )
    unread_only = request.GET.get('unread_only', '').lower() in ('1', 'true', 'yes')
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    qs = qs.order_by('-created_at')
    limit = request.GET.get('limit')
    if limit:
        try:
            qs = qs[: max(1, min(100, int(limit)))]
        except ValueError:
            qs = qs[:50]
    else:
        qs = qs[:50]
    results = [_notification_to_dict(n) for n in qs]
    return JsonResponse({'results': results})


@customer_auth_required
@require_http_methods(['GET'])
def in_app_notification_list_customer(request):
    """List in-app notifications where current customer is recipient."""
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'results': []})
    qs = InAppNotification.objects.filter(recipient_customer_id=customer_id).select_related(
        'sender', 'recipient_user', 'recipient_customer'
    )
    unread_only = request.GET.get('unread_only', '').lower() in ('1', 'true', 'yes')
    if unread_only:
        qs = qs.filter(read_at__isnull=True)
    qs = qs.order_by('-created_at')
    limit = request.GET.get('limit')
    if limit:
        try:
            qs = qs[: max(1, min(100, int(limit)))]
        except ValueError:
            qs = qs[:50]
    else:
        qs = qs[:50]
    results = [_notification_to_dict(n) for n in qs]
    return JsonResponse({'results': results})


# --- Create (super_admin, owner, manager, waiter only) ---

def _allowed_recipient_user_ids(request):
    """Return set of user IDs the current user can send to (staff in scope)."""
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        return set(Staff.objects.values_list('user_id', flat=True).distinct())
    if rid:
        return set(Staff.objects.filter(restaurant_id__in=rid).values_list('user_id', flat=True).distinct())
    return set()


def _allowed_recipient_customer_ids(request):
    """Return set of customer IDs the current user can send to."""
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        restaurant_ids = list(Restaurant.objects.values_list('id', flat=True))
    elif rid:
        restaurant_ids = list(rid)
    else:
        return set()
    links = CustomerRestaurant.objects.filter(restaurant_id__in=restaurant_ids).values_list('customer_id', flat=True).distinct()
    order_customers = Order.objects.filter(restaurant_id__in=restaurant_ids).exclude(
        customer_id__isnull=True
    ).values_list('customer_id', flat=True).distinct()
    return set(links) | set(order_customers)


@auth_required
@csrf_exempt
@require_http_methods(['POST'])
def in_app_notification_create(request):
    """Create in-app notifications (one per recipient). Allowed: super_admin, owner, manager, waiter, kitchen."""
    role = get_role(request.user)
    if role not in ('super_admin', 'owner', 'manager', 'waiter', 'kitchen'):
        return JsonResponse({'error': 'Only Super Admin, Owner, Manager, Waiter, or Kitchen can send notifications.'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    purpose = (body.get('purpose') or body.get('message') or '').strip()
    if not purpose:
        return JsonResponse({'error': 'purpose or message is required'}, status=400)
    recipient_user_ids = body.get('recipient_user_ids') or []
    recipient_customer_ids = body.get('recipient_customer_ids') or []
    if not isinstance(recipient_user_ids, list):
        recipient_user_ids = []
    if not isinstance(recipient_customer_ids, list):
        recipient_customer_ids = []
    allowed_users = _allowed_recipient_user_ids(request)
    allowed_customers = _allowed_recipient_customer_ids(request)
    created = []
    for uid in recipient_user_ids:
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        if uid not in allowed_users:
            return JsonResponse({'error': f'User id {uid} is not an allowed recipient.'}, status=403)
        n = InAppNotification.objects.create(
            sender=request.user,
            recipient_user_id=uid,
            recipient_customer=None,
            purpose=purpose,
        )
        created.append(_notification_to_dict(n))
    for cid in recipient_customer_ids:
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            continue
        if cid not in allowed_customers:
            return JsonResponse({'error': f'Customer id {cid} is not an allowed recipient.'}, status=403)
        n = InAppNotification.objects.create(
            sender=request.user,
            recipient_user=None,
            recipient_customer_id=cid,
            purpose=purpose,
        )
        created.append(_notification_to_dict(n))
    if not created:
        return JsonResponse({'error': 'Select at least one recipient (recipient_user_ids or recipient_customer_ids).'}, status=400)
    return JsonResponse({'results': created, 'count': len(created)}, status=201)


# --- Recipients (for send box multi-select) ---

@auth_required
@require_http_methods(['GET'])
def in_app_notification_recipients(request):
    """Return allowed recipients for the current user (staff + customers) for multi-select."""
    role = get_role(request.user)
    if role not in ('super_admin', 'owner', 'manager', 'waiter', 'kitchen'):
        return JsonResponse({'staff': [], 'customers': []})
    allowed_user_ids = _allowed_recipient_user_ids(request)
    allowed_customer_ids = _allowed_recipient_customer_ids(request)
    staff = []
    if allowed_user_ids:
        users = User.objects.filter(id__in=allowed_user_ids)
        for u in users:
            staff.append({
                'id': u.id,
                'name': getattr(u, 'name', None) or getattr(u, 'username', '') or f'User #{u.id}',
                'type': 'staff',
            })
    customers = []
    if allowed_customer_ids:
        for c in Customer.objects.filter(id__in=allowed_customer_ids):
            customers.append({
                'id': c.id,
                'name': c.name or f'Customer #{c.id}',
                'type': 'customer',
            })
    return JsonResponse({'staff': staff, 'customers': customers})
