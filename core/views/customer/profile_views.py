"""Customer profile: update name, address, fcm_token. Requires customer auth."""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from core.utils import customer_auth_required


@csrf_exempt
@require_http_methods(['PATCH', 'PUT'])
@customer_auth_required
def customer_profile_update(request):
    """
    PATCH/PUT JSON: name, address, fcm_token (all optional).
    Updates request.customer only.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    customer = request.customer
    if 'name' in body and body['name'] is not None:
        customer.name = (body['name'] or '').strip() or customer.name
    if 'address' in body:
        customer.address = (body['address'] or '').strip()
    if 'fcm_token' in body:
        customer.fcm_token = (body['fcm_token'] or '').strip()
    customer.save(update_fields=['name', 'address', 'fcm_token', 'updated_at'])
    return JsonResponse({
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone,
        'country_code': customer.country_code or '',
        'address': customer.address or '',
        'fcm_token': customer.fcm_token or '',
    })


@require_http_methods(['GET'])
@customer_auth_required
def customer_profile_get(request):
    """GET current customer profile."""
    customer = request.customer
    return JsonResponse({
        'id': customer.id,
        'name': customer.name,
        'phone': customer.phone,
        'country_code': customer.country_code or '',
        'address': customer.address or '',
        'fcm_token': customer.fcm_token or '',
    })
