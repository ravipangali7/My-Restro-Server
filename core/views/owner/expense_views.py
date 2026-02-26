"""Owner expenses list, create, update, delete. Function-based."""
import json
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.utils import timezone

from core.models import Expenses, Restaurant, Vendor
from core.utils import get_restaurant_ids, auth_required


def _expense_to_dict(e):
    return {
        'id': e.id,
        'restaurant_id': e.restaurant_id,
        'name': e.name,
        'vendor_id': e.vendor_id,
        'description': e.description or '',
        'amount': str(e.amount),
        'image': e.image.url if e.image else None,
        'created_at': e.created_at.isoformat() if e.created_at else None,
        'updated_at': e.updated_at.isoformat() if e.updated_at else None,
    }


def _expense_qs(request):
    rid = get_restaurant_ids(request)
    if getattr(request.user, 'is_superuser', False):
        qs = Expenses.objects.all()
    elif rid:
        qs = Expenses.objects.filter(restaurant_id__in=rid)
    else:
        qs = Expenses.objects.none()
    return qs


@auth_required
@require_http_methods(['GET'])
def owner_expense_detail(request, pk):
    """Single expense by id for view page."""
    e = get_object_or_404(Expenses, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and e.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    d = _expense_to_dict(e)
    if e.vendor_id:
        d['vendor_name'] = e.vendor.name if e.vendor else None
    return JsonResponse(d)


@auth_required
@require_http_methods(['GET'])
def owner_expense_list(request):
    qs = _expense_qs(request)
    now = timezone.now()
    this_month = qs.filter(created_at__year=now.year, created_at__month=now.month)
    total_this_month = this_month.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    stats = {'total_this_month': str(total_this_month), 'unpaid': 0}
    results = [_expense_to_dict(e) for e in qs.order_by('-created_at')[:100]]
    return JsonResponse({'stats': stats, 'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_expense_create(request):
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
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)
    try:
        amount = Decimal(str(body.get('amount', 0)))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid amount'}, status=400)
    if amount < 0:
        return JsonResponse({'error': 'Amount cannot be negative'}, status=400)
    e = Expenses(
        restaurant=restaurant,
        name=name,
        vendor_id=body.get('vendor_id') or None,
        description=body.get('description', ''),
        amount=amount,
    )
    e.save()
    return JsonResponse(_expense_to_dict(e), status=201)


@csrf_exempt
@auth_required
@require_http_methods(['PUT', 'PATCH'])
def owner_expense_update(request, pk):
    e = get_object_or_404(Expenses, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and e.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if 'name' in body:
        e.name = str(body['name']).strip() or e.name
    if 'vendor_id' in body:
        e.vendor_id = body['vendor_id'] or None
    if 'description' in body:
        e.description = str(body.get('description', ''))
    if 'amount' in body:
        try:
            amt = Decimal(str(body['amount']))
            if amt < 0:
                return JsonResponse({'error': 'Amount cannot be negative'}, status=400)
            e.amount = amt
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({'error': 'Invalid amount'}, status=400)
    e.save()
    return JsonResponse(_expense_to_dict(e))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_expense_upload_image(request, pk):
    """Upload expense image (e.g. receipt). Multipart form with 'image' file."""
    e = get_object_or_404(Expenses, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and e.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'image file required'}, status=400)
    e.image = image_file
    e.save()
    return JsonResponse(_expense_to_dict(e))


@auth_required
@require_http_methods(['DELETE'])
def owner_expense_delete(request, pk):
    e = get_object_or_404(Expenses, pk=pk)
    rid = get_restaurant_ids(request)
    if rid and e.restaurant_id not in rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    e.delete()
    return JsonResponse({'success': True}, status=200)
