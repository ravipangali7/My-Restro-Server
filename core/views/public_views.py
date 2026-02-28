"""Public API (no auth): restaurant and menu by slug for QR menu; public feedback."""
import io
import json
import qrcode
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from core.models import (
    Restaurant, Category, Product, Staff, Attendance, Order, Feedback,
)
from core.fcm import send_fcm_to_token
from core.constants import normalize_country_code
from core.services import get_or_create_customer_for_restaurant


def _restaurant_to_public_dict(r):
    return {
        'id': r.id,
        'name': r.name,
        'slug': r.slug,
        'phone': r.phone or '',
        'address': r.address or '',
        'logo': r.logo.url if r.logo else None,
        'is_open': r.is_open,
    }


def _check_restaurant_active(r):
    """Return None if restaurant is active (is_restaurant=True), else JsonResponse 404 with inactive message."""
    if not getattr(r, 'is_restaurant', True):
        return JsonResponse({'error': 'inactive', 'message': 'Restaurant is inactive'}, status=404)
    return None


def _table_to_public_dict(t):
    return {
        'id': t.id,
        'restaurant_id': t.restaurant_id,
        'name': t.name,
        'capacity': t.capacity,
        'floor': t.floor or '',
        'near_by': t.near_by or '',
        'notes': getattr(t, 'notes', '') or '',
    }


@require_http_methods(['GET'])
def public_restaurant_list(request):
    """GET /api/public/restaurants/ - no auth. Returns list of active restaurants (is_restaurant=True)."""
    qs = Restaurant.objects.filter(is_restaurant=True).order_by('name')
    data = [_restaurant_to_public_dict(r) for r in qs]
    return JsonResponse({'results': data})


@require_http_methods(['GET'])
def public_restaurant_by_id(request, id):
    """GET /api/public/restaurants/<id>/ - no auth. Returns restaurant info; 404 if inactive."""
    r = get_object_or_404(Restaurant, pk=id)
    inactive = _check_restaurant_active(r)
    if inactive:
        return inactive
    return JsonResponse(_restaurant_to_public_dict(r))


@require_http_methods(['GET'])
def public_restaurant_by_slug(request, slug):
    """GET /api/public/restaurant/<slug>/ - no auth. Returns restaurant info; 404 if inactive."""
    r = get_object_or_404(Restaurant, slug=slug)
    inactive = _check_restaurant_active(r)
    if inactive:
        return inactive
    return JsonResponse(_restaurant_to_public_dict(r))


@require_http_methods(['GET'])
def public_restaurant_tables(request, slug):
    """GET /api/public/restaurant/<slug>/tables/ - no auth. Returns tables; 404 if restaurant inactive."""
    r = get_object_or_404(Restaurant, slug=slug)
    inactive = _check_restaurant_active(r)
    if inactive:
        return inactive
    tables = r.tables.order_by('floor', 'name')
    results = [_table_to_public_dict(t) for t in tables]
    return JsonResponse({'results': results})


@require_http_methods(['GET'])
def public_restaurant_qr(request, slug):
    """GET /api/public/restaurant/<slug>/qr/ - no auth. Returns PNG QR code; 404 JSON if restaurant inactive."""
    r = get_object_or_404(Restaurant, slug=slug)
    if not getattr(r, 'is_restaurant', True):
        return JsonResponse({'error': 'inactive', 'message': 'Restaurant is inactive'}, status=404)
    base_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')
    menu_url = f'{base_url}/menu/{r.slug}'
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@require_http_methods(['GET'])
def public_restaurant_menu(request, slug):
    """GET /api/public/restaurant/<slug>/menu/ - no auth. Returns categories and products.
    When restaurant is inactive (is_restaurant=False) or closed (is_open=False), returns empty menu with message."""
    r = get_object_or_404(Restaurant, slug=slug)
    if not getattr(r, 'is_restaurant', True):
        return JsonResponse({
            'restaurant': _restaurant_to_public_dict(r),
            'categories': [],
            'products': [],
            'inactive': True,
            'message': 'Restaurant is inactive',
        })
    if not r.is_open:
        return JsonResponse({
            'restaurant': _restaurant_to_public_dict(r),
            'categories': [],
            'products': [],
        })
    categories = [
        {'id': c.id, 'name': c.name}
        for c in Category.objects.filter(restaurant=r).order_by('name')
    ]
    products_qs = (
        Product.objects.filter(restaurant=r, is_active=True)
        .select_related('category')
        .prefetch_related('variants')
    )
    products = []
    for p in products_qs:
        variants = list(p.variants.all())
        price = str(variants[0].price) if variants else '0'
        products.append({
            'id': p.id,
            'name': p.name,
            'category_id': p.category_id,
            'category_name': p.category.name if p.category else '',
            'price': price,
            'selling_price': price,
            'is_available': p.is_active,
            'is_veg': p.dish_type == 'veg',
            'type': p.dish_type,
        })
    return JsonResponse({
        'restaurant': _restaurant_to_public_dict(r),
        'categories': categories,
        'products': products,
    })


@csrf_exempt
@require_http_methods(['POST'])
def public_feedback_submit(request, slug):
    """
    POST /api/public/restaurant/<slug>/feedback/
    Body: staff_id (required), rating (required), review (optional), order_id (optional), name (optional), phone (optional).
    If name/phone provided, get or create Customer for this restaurant; else require them for guest feedback.
    Creates Feedback linked to restaurant, staff, optional order, and customer.
    """
    r = get_object_or_404(Restaurant, slug=slug)
    if not getattr(r, 'is_restaurant', True):
        return JsonResponse({'error': 'Restaurant is inactive'}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    staff_id = body.get('staff_id')
    if staff_id is None:
        return JsonResponse({'error': 'staff_id required'}, status=400)
    try:
        staff_id = int(staff_id)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid staff_id'}, status=400)
    staff = Staff.objects.filter(pk=staff_id, restaurant=r, is_waiter=True).first()
    if not staff:
        return JsonResponse({'error': 'Invalid staff for this restaurant'}, status=400)
    rating = body.get('rating')
    if rating is None:
        return JsonResponse({'error': 'rating required'}, status=400)
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid rating'}, status=400)
    if not (0 <= rating <= 5):
        return JsonResponse({'error': 'rating must be 0-5'}, status=400)
    review = (body.get('review') or '').strip()
    order_id = body.get('order_id')
    if order_id is not None:
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            order_id = None
    order = None
    if order_id:
        order = Order.objects.filter(pk=order_id, restaurant=r).first()
    name = (body.get('name') or '').strip() or 'Guest'
    phone = (body.get('phone') or '').strip()
    country_code = normalize_country_code((body.get('country_code') or '').strip()) or None
    if not phone:
        return JsonResponse({'error': 'phone required for feedback'}, status=400)
    customer, _ = get_or_create_customer_for_restaurant(r, phone, name=name or phone, country_code=country_code or None)
    if not customer:
        return JsonResponse({'error': 'Could not create customer'}, status=400)
    Feedback.objects.create(
        restaurant=r,
        customer=customer,
        order=order,
        staff=staff,
        rating=rating,
        review=review,
    )
    return JsonResponse({'ok': True})
