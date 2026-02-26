"""Owner/Manager read-only settings (e.g. per_qr_stand_price for QR stand order form)."""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core.models import SuperSetting
from core.utils import auth_required


@auth_required
@require_http_methods(['GET'])
def owner_settings(request):
    """Return public/read-only settings for owner/manager (e.g. per_qr_stand_price, subscription_fee_per_month)."""
    s = SuperSetting.objects.first()
    if not s:
        return JsonResponse({
            'per_qr_stand_price': None,
            'subscription_fee_per_month': None,
            'is_subscription_fee': True,
        })
    return JsonResponse({
        'per_qr_stand_price': str(s.per_qr_stand_price) if s.per_qr_stand_price is not None else None,
        'subscription_fee_per_month': str(s.subscription_fee_per_month) if s.subscription_fee_per_month is not None else None,
        'is_subscription_fee': s.is_subscription_fee,
    })
