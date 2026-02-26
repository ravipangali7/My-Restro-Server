"""Delivery tracking: list, detail, assign rider, update status, rider location. Owner/Manager/Waiter scope."""
import json
from datetime import datetime
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import (
    Order,
    Delivery,
    Rider,
    Restaurant,
    OrderType,
    DeliveryStatus,
    RiderSource,
)
from core.utils import auth_required, get_restaurant_ids
from core.delivery.utils import (
    haversine_km_decimal,
    compute_distance_eta,
)
from core.delivery.providers import get_provider


def _delivery_qs(request):
    """Delivery queryset scoped to request user's restaurants."""
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return Delivery.objects.none()
    qs = Delivery.objects.select_related(
        'order', 'order__restaurant', 'order__customer', 'rider'
    ).filter(order__restaurant_id__in=rid) if rid else Delivery.objects.select_related(
        'order', 'order__restaurant', 'order__customer', 'rider'
    )
    return qs


def _delivery_to_dict(d):
    """Serialize Delivery for API."""
    rider = d.rider
    out = {
        'order_id': d.order_id,
        'delivery_status': d.delivery_status,
        'address': d.order.address or '',
        'pickup_lat': float(d.pickup_lat) if d.pickup_lat is not None else None,
        'pickup_lon': float(d.pickup_lon) if d.pickup_lon is not None else None,
        'delivery_lat': float(d.delivery_lat) if d.delivery_lat is not None else None,
        'delivery_lon': float(d.delivery_lon) if d.delivery_lon is not None else None,
        'rider_lat': float(d.rider_lat) if d.rider_lat is not None else None,
        'rider_lon': float(d.rider_lon) if d.rider_lon is not None else None,
        'distance_km': float(d.distance_km) if d.distance_km is not None else None,
        'eta_minutes': d.eta_minutes,
        'assigned_at': d.assigned_at.isoformat() if d.assigned_at else None,
        'picked_up_at': d.picked_up_at.isoformat() if d.picked_up_at else None,
        'delivered_at': d.delivered_at.isoformat() if d.delivered_at else None,
        'rider': None,
        'customer_name': d.order.customer.name if d.order.customer else None,
        'created_at': d.created_at.isoformat() if d.created_at else None,
        'updated_at': d.updated_at.isoformat() if d.updated_at else None,
    }
    if rider:
        out['rider'] = {
            'id': rider.id,
            'name': rider.name,
            'phone': rider.phone,
            'source': rider.source,
        }
    return out


def _push_tracking_update(delivery_id, payload):
    """Push tracking update to WebSocket channel group. No-op if channels not configured."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'tracking_delivery_{delivery_id}',
                {'type': 'tracking.update', 'payload': payload},
            )
    except Exception:
        pass


@auth_required
@require_http_methods(['GET'])
def owner_rider_list(request):
    """List all riders (for admin / assign UI)."""
    riders = list(Rider.objects.order_by('name').values('id', 'name', 'phone', 'source', 'is_available'))
    return JsonResponse({'results': riders})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_rider_create(request):
    """Create an in-house rider. Body: { "name", "phone" }."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    name = (body.get('name') or '').strip()
    phone = (body.get('phone') or '').strip()
    if not name or not phone:
        return JsonResponse({'error': 'name and phone required'}, status=400)
    rider = Rider.objects.create(name=name, phone=phone, source=RiderSource.IN_HOUSE, is_available=True)
    return JsonResponse({
        'id': rider.id,
        'name': rider.name,
        'phone': rider.phone,
        'source': rider.source,
        'is_available': rider.is_available,
    }, status=201)


@auth_required
@require_http_methods(['POST'])
def owner_delivery_ensure(request):
    """Ensure Delivery exists for order (create if accepted delivery order). Body: { "order_id" }."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    order_id = body.get('order_id')
    if not order_id:
        return JsonResponse({'error': 'order_id required'}, status=400)
    order_id = int(order_id)
    qs = Order.objects.filter(pk=order_id)
    rid = get_restaurant_ids(request)
    if rid:
        qs = qs.filter(restaurant_id__in=rid)
    elif not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    o = get_object_or_404(qs.select_related('restaurant'))
    if o.order_type != OrderType.DELIVERY:
        return JsonResponse({'error': 'Not a delivery order'}, status=400)
    d, created = Delivery.objects.get_or_create(
        order=o,
        defaults={
            'delivery_status': DeliveryStatus.ACCEPTED,
            'pickup_lat': o.restaurant.latitude,
            'pickup_lon': o.restaurant.longitude,
            'delivery_lat': o.delivery_lat,
            'delivery_lon': o.delivery_lon,
        }
    )
    return JsonResponse(_delivery_to_dict(d), status=201 if created else 200)


@auth_required
@require_http_methods(['GET'])
def owner_delivery_list(request):
    """List active (live) deliveries for dashboard map. Excludes delivered/returned."""
    qs = _delivery_qs(request)
    qs = qs.exclude(
        delivery_status__in=[DeliveryStatus.DELIVERED, DeliveryStatus.RETURNED]
    ).order_by('-created_at')
    results = [_delivery_to_dict(d) for d in qs[:50]]
    return JsonResponse({'results': results})


@auth_required
@require_http_methods(['GET'])
def owner_delivery_detail(request, pk):
    """Delivery detail by order_id (pk). For map and tracking."""
    qs = _delivery_qs(request)
    d = get_object_or_404(qs, order_id=pk)
    return JsonResponse(_delivery_to_dict(d))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_delivery_update_status(request, pk):
    """Update delivery_status. Body: { "delivery_status": "rider_picked_up" } etc."""
    qs = _delivery_qs(request)
    d = get_object_or_404(qs, order_id=pk)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    new_status = (body.get('delivery_status') or '').strip()
    if not new_status or new_status not in [s[0] for s in DeliveryStatus.choices]:
        return JsonResponse({'error': 'Invalid delivery_status'}, status=400)
    d.delivery_status = new_status
    now = timezone.now()
    if new_status == DeliveryStatus.RIDER_PICKED_UP:
        d.picked_up_at = now
    elif new_status == DeliveryStatus.DELIVERED or new_status == DeliveryStatus.RETURNED:
        d.delivered_at = now
        if new_status == DeliveryStatus.DELIVERED:
            d.order.status = 'served'
            d.order.save(update_fields=['status'])
        if d.rider_id and d.rider:
            d.rider.is_available = True
            d.rider.save(update_fields=['is_available'])
    d.save(update_fields=['delivery_status', 'picked_up_at', 'delivered_at'])
    _push_tracking_update(d.order_id, {
        'delivery_status': d.delivery_status,
        'rider_lat': float(d.rider_lat) if d.rider_lat else None,
        'rider_lon': float(d.rider_lon) if d.rider_lon else None,
        'distance_km': float(d.distance_km) if d.distance_km else None,
        'eta_minutes': d.eta_minutes,
    })
    return JsonResponse(_delivery_to_dict(d))


@auth_required
@require_http_methods(['POST'])
def owner_nearby_riders(request):
    """Find nearest available riders. Body: { "delivery_id" or "order_id" }. Returns list of riders with distance_km."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    order_id = body.get('order_id') or body.get('delivery_id')
    if not order_id:
        return JsonResponse({'error': 'order_id or delivery_id required'}, status=400)
    order_id = int(order_id)
    rid = get_restaurant_ids(request)
    if not rid and not getattr(request.user, 'is_superuser', False):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    restaurant_ids = list(rid) if rid else list(Restaurant.objects.values_list('id', flat=True))
    o = get_object_or_404(
        Order.objects.select_related('restaurant'),
        pk=order_id,
        restaurant_id__in=restaurant_ids
    )
    if o.order_type != OrderType.DELIVERY:
        return JsonResponse({'error': 'Order is not a delivery order'}, status=400)
    # Pickup point: restaurant or delivery pickup
    pickup_lat = getattr(o.restaurant, 'latitude', None) or (getattr(o, 'delivery_lat', None))
    pickup_lon = getattr(o.restaurant, 'longitude', None) or (getattr(o, 'delivery_lon', None))
    if pickup_lat is None or pickup_lon is None:
        # No coords: return all available in-house riders
        riders = list(Rider.objects.filter(is_available=True, source=RiderSource.IN_HOUSE).order_by('name')[:20])
        return JsonResponse({
            'results': [
                {'id': r.id, 'name': r.name, 'phone': r.phone, 'distance_km': None}
                for r in riders
            ]
        })
    pickup_lat = float(pickup_lat)
    pickup_lon = float(pickup_lon)
    riders = list(Rider.objects.filter(is_available=True, source=RiderSource.IN_HOUSE))
    with_dist = []
    for r in riders:
        if r.last_lat is not None and r.last_lon is not None:
            km = haversine_km_decimal(
                Decimal(str(r.last_lat)), Decimal(str(r.last_lon)),
                Decimal(str(pickup_lat)), Decimal(str(pickup_lon))
            )
            with_dist.append((r, round(km, 2) if km is not None else None))
        else:
            with_dist.append((r, None))
    with_dist.sort(key=lambda x: (x[1] is None, x[1] or 999999))
    results = [
        {'id': r.id, 'name': r.name, 'phone': r.phone, 'distance_km': dist}
        for r, dist in with_dist[:20]
    ]
    return JsonResponse({'results': results})


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_assign_rider(request):
    """Assign rider to delivery. Body: { "order_id", "rider_id" }."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    order_id = body.get('order_id')
    rider_id = body.get('rider_id')
    if not order_id or not rider_id:
        return JsonResponse({'error': 'order_id and rider_id required'}, status=400)
    order_id = int(order_id)
    rider_id = int(rider_id)
    qs = _delivery_qs(request)
    d = get_object_or_404(qs, order_id=order_id)
    rider = get_object_or_404(Rider, pk=rider_id)
    d.rider_id = rider_id
    d.delivery_status = DeliveryStatus.RIDER_ASSIGNED
    d.assigned_at = timezone.now()
    rider.is_available = False
    rider.save(update_fields=['is_available'])
    # Set rider_lat/lon from rider's last known position
    if rider.last_lat is not None and rider.last_lon is not None:
        d.rider_lat = rider.last_lat
        d.rider_lon = rider.last_lon
        dist, eta = compute_distance_eta(
            d.rider_lat, d.rider_lon,
            d.delivery_lat, d.delivery_lon
        )
        if dist is not None:
            d.distance_km = Decimal(str(dist))
        if eta is not None:
            d.eta_minutes = eta
    d.save()
    payload = _delivery_to_dict(d)
    _push_tracking_update(d.order_id, {
        'delivery_status': d.delivery_status,
        'rider': payload['rider'],
        'rider_lat': payload['rider_lat'],
        'rider_lon': payload['rider_lon'],
        'distance_km': payload['distance_km'],
        'eta_minutes': payload['eta_minutes'],
    })
    return JsonResponse(payload)


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_rider_location(request):
    """Rider location update. Body: { "order_id", "lat", "lon" }. Updates Delivery + Rider, recomputes ETA, pushes WS."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    order_id = body.get('order_id')
    try:
        lat = float(body.get('lat'))
        lon = float(body.get('lon'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'lat and lon required as numbers'}, status=400)
    qs = _delivery_qs(request)
    d = get_object_or_404(qs, order_id=order_id)
    if not d.rider_id:
        return JsonResponse({'error': 'No rider assigned'}, status=400)
    d.rider_lat = Decimal(str(lat))
    d.rider_lon = Decimal(str(lon))
    dist, eta = compute_distance_eta(
        d.rider_lat, d.rider_lon,
        d.delivery_lat, d.delivery_lon
    )
    if dist is not None:
        d.distance_km = Decimal(str(dist))
    if eta is not None:
        d.eta_minutes = eta
    d.save(update_fields=['rider_lat', 'rider_lon', 'distance_km', 'eta_minutes', 'updated_at'])
    r = d.rider
    r.last_lat = Decimal(str(lat))
    r.last_lon = Decimal(str(lon))
    r.last_updated = timezone.now()
    r.save(update_fields=['last_lat', 'last_lon', 'last_updated'])
    payload = {
        'rider_lat': lat,
        'rider_lon': lon,
        'distance_km': float(d.distance_km) if d.distance_km else None,
        'eta_minutes': d.eta_minutes,
        'delivery_status': d.delivery_status,
    }
    _push_tracking_update(d.order_id, payload)
    return JsonResponse(_delivery_to_dict(d))


@csrf_exempt
@auth_required
@require_http_methods(['POST'])
def owner_request_third_party_ride(request):
    """Request ride via Pathao/Yango. Body: { "order_id", "source": "pathao"|"yango" }."""
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    order_id = body.get('order_id')
    source = (body.get('source') or '').strip().lower()
    if not order_id or source not in ('pathao', 'yango'):
        return JsonResponse({'error': 'order_id and source (pathao|yango) required'}, status=400)
    order_id = int(order_id)
    qs = _delivery_qs(request)
    d = get_object_or_404(qs, order_id=order_id)
    if d.pickup_lat is None or d.pickup_lon is None or d.delivery_lat is None or d.delivery_lon is None:
        return JsonResponse({'error': 'Delivery pickup/delivery coordinates required'}, status=400)
    provider = get_provider(source)
    if not provider:
        return JsonResponse({'error': 'Unknown provider'}, status=400)
    result = provider.request_ride(
        d.pickup_lat, d.pickup_lon,
        d.delivery_lat, d.delivery_lon,
        order_id,
    )
    request_id = result.get('request_id', '')
    d.third_party_request_id = request_id
    d.save(update_fields=['third_party_request_id'])
    # Create a logical Rider for this third-party request
    rider = Rider.objects.create(
        name=f'{source.title()} Rider',
        phone=request_id or '—',
        source=RiderSource.PATHAO if source == 'pathao' else RiderSource.YANGO,
        is_available=False,
    )
    d.rider_id = rider.id
    d.delivery_status = DeliveryStatus.RIDER_ASSIGNED
    d.assigned_at = timezone.now()
    d.save(update_fields=['rider_id', 'delivery_status', 'assigned_at'])
    _push_tracking_update(d.order_id, {
        'delivery_status': d.delivery_status,
        'rider': {'id': rider.id, 'name': rider.name, 'phone': rider.phone or '—', 'source': rider.source},
    })
    return JsonResponse({
        'request_id': request_id,
        'delivery': _delivery_to_dict(d),
        'message': result.get('message', ''),
    })
