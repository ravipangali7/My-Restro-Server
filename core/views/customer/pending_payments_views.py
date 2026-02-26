"""Customer pending payments: to_pay / to_receive per restaurant via CustomerRestaurant."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.utils import customer_auth_required, get_customer_id_from_request


@require_http_methods(['GET'])
@customer_auth_required
def customer_pending_payments(request):
    """
    GET list of CustomerRestaurant for request.customer: restaurant_id, restaurant_name, to_pay, to_receive.
    """
    customer_id = get_customer_id_from_request(request)
    if not customer_id:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    from core.models import CustomerRestaurant
    qs = CustomerRestaurant.objects.filter(customer_id=customer_id).select_related('restaurant')
    results = [
        {
            'id': cr.id,
            'restaurant_id': cr.restaurant_id,
            'restaurant_name': cr.restaurant.name if cr.restaurant else None,
            'to_pay': str(cr.to_pay),
            'to_receive': str(cr.to_receive),
        }
        for cr in qs
    ]
    return JsonResponse({'results': results})

