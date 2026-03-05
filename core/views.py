from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import (
    User,
    Restaurant,
    SuperSetting,
    ShareholderWithdrawal,
    Transaction,
    TransactionType,
    TransactionCategory,
    WithdrawalStatus,
    QrStandOrder,
    QrStandOrderStatus,
    KycStatus,
    BulkNotification,
    Customer,
    Staff,
    Vendor,
    Order,
    CustomerRestaurant,
    Attendance,
    PaidRecord,
    AttendanceStatus,
)
from .models import PaymentStatus
from .permissions import IsSuperuser, IsSuperuserOrOwner
from .serializers import (
    OwnerSerializer,
    OwnerCreateUpdateSerializer,
    OwnerDetailSerializer,
    UserSerializer,
    RestaurantListSerializer,
    RestaurantDetailSerializer,
    RestaurantCreateUpdateSerializer,
    RestaurantMinSerializer,
    ShareholderWithdrawalSerializer,
    ShareholderWithdrawalListSerializer,
    ShareholderWithdrawalCreateSerializer,
    ShareholderWithdrawalDetailSerializer,
    TransactionSerializer,
    TransactionDetailSerializer,
    SuperSettingSerializer,
    SuperSettingUpdateSerializer,
    QrStandOrderListSerializer,
    QrStandOrderDetailSerializer,
    QrStandOrderCreateSerializer,
    QrStandOrderUpdateSerializer,
    BulkNotificationListSerializer,
    BulkNotificationDetailSerializer,
    BulkNotificationCreateUpdateSerializer,
    CustomerListSerializer,
    OwnerStaffListSerializer,
    OwnerStaffCreateUpdateSerializer,
    OwnerVendorListSerializer,
    OwnerVendorCreateUpdateSerializer,
)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _owner_restaurant_ids(request):
    """Return list of restaurant IDs for request.user when owner; else None (no filter)."""
    if not getattr(request.user, 'is_owner', False):
        return None
    return list(Restaurant.objects.filter(user=request.user).values_list('id', flat=True))


def _parse_date_range(request):
    """Return (start_dt, end_dt) from query params: range preset or start_date/end_date."""
    range_preset = (request.query_params.get('range') or '').strip().lower()
    now = timezone.now()
    if range_preset == 'last_24h' or range_preset == 'last_24_hour':
        return now - timedelta(hours=24), now
    if range_preset == 'week':
        return now - timedelta(days=7), now
    if range_preset == 'month':
        return now - timedelta(days=30), now
    start_s = request.query_params.get('start_date')
    end_s = request.query_params.get('end_date')
    if start_s and end_s:
        try:
            from datetime import datetime
            start_dt = timezone.make_aware(datetime.strptime(start_s[:10], '%Y-%m-%d'))
            end_dt = timezone.make_aware(datetime.strptime(end_s[:10], '%Y-%m-%d'))
            if end_dt < start_dt:
                start_dt, end_dt = end_dt, start_dt
            return start_dt, end_dt
        except Exception:
            pass
    return None, None


def _owner_queryset(request):
    qs = User.objects.filter(is_owner=True).order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(country_code__icontains=search)
        )
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    return qs


# ---------- Owners ----------

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuser])
def owner_list(request):
    if request.method == 'POST':
        serializer = OwnerCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            user = serializer.instance
            return Response(OwnerSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = _owner_queryset(request)
    ordering = request.query_params.get('ordering') or request.query_params.get('sort') or '-created_at'
    allowed = ['created_at', '-created_at', 'name', '-name', 'phone', '-phone', 'balance', '-balance']
    if ordering.lstrip('-') in [f.lstrip('-') for f in allowed]:
        qs = qs.order_by(ordering)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = OwnerSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def owner_search(request):
    phone = (request.query_params.get('phone') or '').strip()
    country_code = (request.query_params.get('country_code') or '').strip()
    if not phone:
        return Response({'detail': 'phone required'}, status=status.HTTP_400_BAD_REQUEST)
    qs = User.objects.filter(phone=phone)
    if country_code:
        qs = qs.filter(country_code=country_code)
    user = qs.first()
    if not user:
        return Response({'found': False, 'user': None})
    return Response({
        'found': True,
        'user': UserSerializer(user).data,
    })


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuser])
def owner_detail(request, pk):
    try:
        user = User.objects.get(pk=pk, is_owner=True)
    except User.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = OwnerDetailSerializer(user, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = OwnerCreateUpdateSerializer(user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    # DELETE
    user.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def owner_stats(request):
    owners = User.objects.filter(is_owner=True)
    total_owner = owners.count()
    kyc_pending = owners.filter(kyc_status='pending').count()
    from .models import KycStatus
    approved = owners.filter(kyc_status=KycStatus.APPROVED).count()
    rejected = owners.filter(kyc_status=KycStatus.REJECTED).count()
    # Active owner: has at least one restaurant that is open (is_open=True)
    active_owner = owners.filter(restaurants__is_open=True).distinct().count()
    # Restro expired: has restaurant(s) with subscription_end < today
    from django.utils import timezone as tz
    today = tz.now().date()
    restro_expired = owners.filter(restaurants__subscription_end__lt=today).distinct().count()
    # Total revenue: sum of balance from all owners (or from SuperSetting - using owners balance sum as proxy)
    total_revenue = owners.aggregate(s=Sum('balance'))['s'] or 0
    return Response({
        'total_owner': total_owner,
        'active_owner': active_owner,
        'total_revenue': str(total_revenue),
        'restro_expired_owner': restro_expired,
        'kyc_pending_owner': kyc_pending,
        'kyc_approved': approved,
        'kyc_rejected': rejected,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def owner_analytics(request):
    owners = User.objects.filter(is_owner=True)
    kyc_pending = owners.filter(kyc_status=KycStatus.PENDING).count()
    kyc_approved = owners.filter(kyc_status=KycStatus.APPROVED).count()
    kyc_rejected = owners.filter(kyc_status=KycStatus.REJECTED).count()
    kyc_status_distribution = [
        {'status': 'pending', 'count': kyc_pending},
        {'status': 'approved', 'count': kyc_approved},
        {'status': 'rejected', 'count': kyc_rejected},
    ]
    # Registration trend by month
    reg_qs = owners.annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(count=Count('id')).order_by('month_key')
    registration_trend = []
    for row in reg_qs:
        mk = row['month_key']
        month_str = mk.strftime('%Y-%m') if hasattr(mk, 'strftime') else str(mk)[:7]
        registration_trend.append({'month': month_str, 'count': row['count']})
    # Owner restaurant count (bar chart)
    owner_count_qs = Restaurant.objects.values('user__name', 'user_id').annotate(restaurant_count=Count('id')).order_by('-restaurant_count')
    owner_restaurant_count = [{'owner_name': r['user__name'] or f"User #{r['user_id']}", 'restaurant_count': r['restaurant_count']} for r in owner_count_qs]
    return Response({
        'kyc_status_distribution': kyc_status_distribution,
        'registration_trend': registration_trend,
        'owner_restaurant_count': owner_restaurant_count,
    })


# ---------- Restaurants ----------

def _restaurant_queryset(request, restrict_to_owner=True):
    qs = Restaurant.objects.all().select_related('user').order_by('-created_at')
    if restrict_to_owner:
        owner_ids = _owner_restaurant_ids(request)
        if owner_ids is not None:
            qs = qs.filter(id__in=owner_ids)
    if request.query_params.get('has_due') == 'true':
        qs = qs.filter(due_balance__gt=0)
    if request.query_params.get('subscription_expired') == 'true':
        today = timezone.now().date()
        qs = qs.filter(subscription_end__lt=today)
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(slug__icontains=search) |
            Q(phone__icontains=search) |
            Q(address__icontains=search) |
            Q(user__name__icontains=search)
        )
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    return qs


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def restaurant_list(request):
    if request.method == 'POST':
        serializer = RestaurantCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                RestaurantDetailSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = _restaurant_queryset(request)
    ordering = request.query_params.get('ordering') or request.query_params.get('sort') or '-created_at'
    allowed = ['created_at', '-created_at', 'name', '-name', 'slug', '-slug']
    if ordering.lstrip('-') in [f.lstrip('-') for f in allowed]:
        qs = qs.order_by(ordering)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = RestaurantListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def restaurant_detail(request, pk):
    try:
        rest = Restaurant.objects.select_related('user').get(pk=pk)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    # Owner can only access their own restaurant
    if not request.user.is_superuser and rest.user_id != request.user.id:
        return Response({'detail': 'You do not have permission to access this restaurant.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        serializer = RestaurantDetailSerializer(rest, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = RestaurantCreateUpdateSerializer(rest, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(RestaurantDetailSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        if not request.user.is_superuser:
            return Response({'detail': 'Only superuser can delete restaurants.'}, status=status.HTTP_403_FORBIDDEN)
    rest.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def restaurant_stats(request):
    qs = Restaurant.objects.all()
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(id__in=owner_ids)
    total = qs.count()
    active = qs.filter(is_open=True).count()
    inactive = qs.filter(is_open=False).count()
    from django.utils import timezone as tz
    today = tz.now().date()
    expired = qs.filter(subscription_end__lt=today).count()
    agg = qs.aggregate(total_due=Sum('due_balance'), total_balance=Sum('balance'))
    total_due = agg['total_due'] or 0
    total_revenue = agg['total_balance'] or 0
    return Response({
        'total_restaurants': total,
        'active': active,
        'inactive': inactive,
        'expired_subscription': expired,
        'total_due': str(total_due),
        'total_revenue': str(total_revenue),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def restaurant_analytics(request):
    from django.utils import timezone as tz
    today = tz.now().date()
    qs = Restaurant.objects.all()
    # Status distribution: active, inactive, expired
    active = qs.filter(is_open=True).count()
    inactive = qs.filter(is_open=False).count()
    expired = qs.filter(subscription_end__lt=today).count()
    status_distribution = [
        {'status': 'active', 'count': active},
        {'status': 'inactive', 'count': inactive},
        {'status': 'expired', 'count': expired},
    ]
    # New restaurants growth by month
    growth_qs = Restaurant.objects.annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(count=Count('id')).order_by('month_key')
    new_restaurants_growth = []
    for row in growth_qs:
        mk = row['month_key']
        month_str = mk.strftime('%Y-%m') if hasattr(mk, 'strftime') else str(mk)[:7]
        new_restaurants_growth.append({'month': month_str, 'count': row['count']})
    # Balance comparison: top 10 and bottom 10
    top10 = list(qs.order_by('-balance').values('name', 'balance')[:10])
    bottom10 = list(qs.order_by('balance').values('name', 'balance')[:10])
    balance_comparison = {
        'top_10': [{'restaurant_name': r['name'], 'balance': float(r['balance'] or 0)} for r in top10],
        'bottom_10': [{'restaurant_name': r['name'], 'balance': float(r['balance'] or 0)} for r in bottom10],
    }
    return Response({
        'status_distribution': status_distribution,
        'new_restaurants_growth': new_restaurants_growth,
        'balance_comparison': balance_comparison,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def due_stats(request):
    """Stats for Due listing: total due count/amount, over threshold, outstanding."""
    qs_with_due = Restaurant.objects.filter(due_balance__gt=0)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs_with_due = qs_with_due.filter(id__in=owner_ids)
    total_due_count = qs_with_due.count()
    total_due_amount = qs_with_due.aggregate(s=Sum('due_balance'))['s'] or 0
    try:
        ss = SuperSetting.objects.first()
        threshold = (ss.due_threshold or 0) if ss else 0
    except Exception:
        threshold = 0
    over_threshold_qs = qs_with_due.filter(due_balance__gt=threshold) if threshold else qs_with_due
    over_threshold_count = over_threshold_qs.count()
    over_threshold_amount = over_threshold_qs.aggregate(s=Sum('due_balance'))['s'] or 0
    return Response({
        'total_due_count': total_due_count,
        'total_due_amount': str(total_due_amount),
        'over_threshold_count': over_threshold_count,
        'over_threshold_amount': str(over_threshold_amount),
        'outstanding_count': total_due_count,
        'outstanding_amount': str(total_due_amount),
    })


# ---------- Owner (dashboard & scoped data) ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_dashboard_stats(request):
    """Owner-scoped dashboard: restaurants count, staff count, revenue, due, recent activity."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None:
        return Response({'detail': 'Not available for superuser. Use dashboard-stats.'}, status=status.HTTP_403_FORBIDDEN)
    if not owner_ids:
        return Response({
            'restaurants_count': 0,
            'staff_count': 0,
            'total_revenue': '0',
            'total_due': '0',
            'active_restaurants': 0,
            'recent_transactions': [],
        })
    qs_rest = Restaurant.objects.filter(id__in=owner_ids)
    restaurants_count = qs_rest.count()
    active_restaurants = qs_rest.filter(is_open=True).count()
    total_due = qs_rest.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    total_revenue = qs_rest.aggregate(s=Sum('balance'))['s'] or Decimal('0')
    staff_count = Staff.objects.filter(restaurant_id__in=owner_ids).count()
    recent = Transaction.objects.filter(restaurant_id__in=owner_ids).order_by('-created_at')[:10]
    recent_data = [
        {
            'id': t.id,
            'reference': getattr(t, 'reference', ''),
            'amount': str(t.amount),
            'transaction_type': getattr(t, 'transaction_type', ''),
            'category': getattr(t, 'category', ''),
            'payment_status': getattr(t, 'payment_status', ''),
            'created_at': t.created_at.isoformat() if hasattr(t.created_at, 'isoformat') else str(t.created_at),
        }
        for t in recent
    ]
    return Response({
        'restaurants_count': restaurants_count,
        'staff_count': staff_count,
        'total_revenue': str(total_revenue),
        'total_due': str(total_due),
        'active_restaurants': active_restaurants,
        'recent_transactions': recent_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_available_users(request):
    """List users that can be assigned as staff (is_restaurant_staff). Optional search and restaurant_id to exclude already-assigned."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    search = (request.query_params.get('search') or '').strip()
    restaurant_id = request.query_params.get('restaurant_id')
    try:
        rid = int(restaurant_id) if restaurant_id else None
    except ValueError:
        rid = None
    if rid is not None and rid not in owner_ids:
        rid = None
    qs = User.objects.filter(is_restaurant_staff=True).exclude(is_superuser=True).order_by('name', 'phone')
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
    if rid is not None:
        already_staff_ids = list(Staff.objects.filter(restaurant_id=rid).values_list('user_id', flat=True))
        if already_staff_ids:
            qs = qs.exclude(id__in=already_staff_ids)
    qs = qs[:100]
    results = [{'id': u.id, 'name': u.name or '', 'phone': u.phone or ''} for u in qs]
    return Response({'results': results})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_list(request):
    """List staff for owner's restaurants; search, pagination, filter active/inactive. POST to create."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        serializer = OwnerStaffCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                OwnerStaffListSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Staff.objects.filter(restaurant_id__in=owner_ids).select_related('user', 'restaurant').order_by('restaurant__name', 'user__name')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(user__name__icontains=search) | Q(user__phone__icontains=search)
        )
    status_filter = request.query_params.get('status', '').strip().lower()
    if status_filter == 'active':
        qs = qs.filter(is_suspend=False)
    elif status_filter == 'inactive':
        qs = qs.filter(is_suspend=True)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = OwnerStaffListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_stats(request):
    """Total, active, inactive staff and total due for owner's restaurants."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total': 0, 'active': 0, 'inactive': 0, 'total_due': '0'})
    qs = Staff.objects.filter(restaurant_id__in=owner_ids)
    total = qs.count()
    active = qs.filter(is_suspend=False).count()
    inactive = qs.filter(is_suspend=True).count()
    total_due = qs.aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
    return Response({
        'total': total,
        'active': active,
        'inactive': inactive,
        'total_due': str(total_due),
    })


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_detail(request, pk):
    """Get or update a single staff; owner can only access staff of their restaurants."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        staff = Staff.objects.select_related('user', 'restaurant').get(pk=pk)
    except Staff.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if staff.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = OwnerStaffListSerializer(staff, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = OwnerStaffCreateUpdateSerializer(staff, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerStaffListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_customers_list(request):
    """List customers with orders in owner's restaurants; total_orders, total_spent, credit_due."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    qs = Customer.objects.filter(orders__restaurant_id__in=owner_ids).distinct().annotate(
        total_orders=Count('orders'),
        total_spent=Coalesce(Sum('orders__total'), Value(Decimal('0'))),
    ).order_by('-total_spent')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = []
    for c in page:
        credit_qs = CustomerRestaurant.objects.filter(customer=c, restaurant_id__in=owner_ids).aggregate(s=Sum('to_pay'))
        credit_due = credit_qs['s'] or Decimal('0')
        results.append({
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'country_code': getattr(c, 'country_code', ''),
            'total_orders': getattr(c, 'total_orders', 0),
            'total_spent': str(getattr(c, 'total_spent', 0)),
            'credit_due': str(credit_due),
        })
    return paginator.get_paginated_response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_customers_stats(request):
    """Total customers, VIP count (e.g. 50+ orders), credit_due sum for owner scope."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total': 0, 'vip_count': 0, 'credit_due': '0'})
    qs = Customer.objects.filter(orders__restaurant_id__in=owner_ids).distinct().annotate(
        order_count=Count('orders'),
        total_spent=Coalesce(Sum('orders__total'), Value(Decimal('0'))),
    )
    total = qs.count()
    vip_count = sum(1 for c in qs if getattr(c, 'order_count', 0) >= 50)
    credit_agg = CustomerRestaurant.objects.filter(restaurant_id__in=owner_ids).aggregate(s=Sum('to_pay'))
    credit_due = credit_agg['s'] or Decimal('0')
    return Response({
        'total': total,
        'vip_count': vip_count,
        'credit_due': str(credit_due),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_vendors_list(request):
    """List vendors for owner's restaurants; search, pagination. POST to create."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        serializer = OwnerVendorCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(
                OwnerVendorListSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Vendor.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant').order_by('name')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(phone__icontains=search))
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = OwnerVendorListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_vendor_detail(request, pk):
    """Get or update a single vendor; owner can only access vendors of their restaurants."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        vendor = Vendor.objects.select_related('restaurant').get(pk=pk)
    except Vendor.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if vendor.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = OwnerVendorListSerializer(vendor, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = OwnerVendorCreateUpdateSerializer(vendor, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerVendorListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_vendors_stats(request):
    """Total vendors, sum to_pay, sum to_receive for owner's restaurants."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total': 0, 'total_to_pay': '0', 'total_to_receive': '0'})
    qs = Vendor.objects.filter(restaurant_id__in=owner_ids)
    total = qs.count()
    agg = qs.aggregate(to_pay=Sum('to_pay'), to_receive=Sum('to_receive'))
    return Response({
        'total': total,
        'total_to_pay': str(agg['to_pay'] or 0),
        'total_to_receive': str(agg['to_receive'] or 0),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_payroll_list(request):
    """Payroll list for owner's staff: staff, restaurant, period, days, per_day, total salary, paid/due, status."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is None or end_dt is None:
        from datetime import datetime
        today = timezone.now().date()
        start_dt = timezone.make_aware(datetime(today.year, today.month, 1))
        end_dt = timezone.now()
    staff_qs = Staff.objects.filter(restaurant_id__in=owner_ids).select_related('user', 'restaurant').order_by('restaurant__name', 'user__name')
    results = []
    for s in staff_qs:
        days = Attendance.objects.filter(
            staff=s, date__gte=start_dt.date(), date__lte=end_dt.date(),
            status=AttendanceStatus.PRESENT,
        ).count()
        per_day = s.per_day_salary or Decimal('0')
        total_salary = per_day * days
        paid_in_period = PaidRecord.objects.filter(staff=s, created_at__gte=start_dt, created_at__lte=end_dt).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        due = max(Decimal('0'), total_salary - paid_in_period)
        role = 'manager' if s.is_manager else ('waiter' if s.is_waiter else ('kitchen' if s.is_kitchen else 'staff'))
        results.append({
            'id': s.id,
            'staff_name': s.user.name if s.user_id else '',
            'restaurant_id': s.restaurant_id,
            'restaurant_name': s.restaurant.name if s.restaurant_id else '',
            'period_start': start_dt.date().isoformat(),
            'period_end': end_dt.date().isoformat(),
            'days': days,
            'per_day_salary': str(per_day),
            'total_salary': str(total_salary),
            'paid': str(paid_in_period),
            'due': str(due),
            'status': 'paid' if due == 0 else 'pending',
        })
    return Response({'count': len(results), 'next': None, 'previous': None, 'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_staff(request):
    """Staff report: filters restaurant, date range, role; table Staff, Restaurant, Role, Attendance days, Salary, Paid, Due, Status."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    start_dt, end_dt = _parse_date_range(request)
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid not in owner_ids:
                rid = None
        except ValueError:
            rid = None
    else:
        rid = None
    qs = Staff.objects.filter(restaurant_id__in=owner_ids)
    if rid is not None:
        qs = qs.filter(restaurant_id=rid)
    role_filter = request.query_params.get('role', '').strip().lower()
    if role_filter == 'manager':
        qs = qs.filter(is_manager=True)
    elif role_filter == 'waiter':
        qs = qs.filter(is_waiter=True)
    elif role_filter == 'kitchen':
        qs = qs.filter(is_kitchen=True)
    qs = qs.select_related('user', 'restaurant').order_by('restaurant__name', 'user__name')
    results = []
    for s in qs:
        if start_dt and end_dt:
            days = Attendance.objects.filter(staff=s, date__gte=start_dt.date(), date__lte=end_dt.date(), status=AttendanceStatus.PRESENT).count()
        else:
            days = Attendance.objects.filter(staff=s, status=AttendanceStatus.PRESENT).count()
        role = 'manager' if s.is_manager else ('waiter' if s.is_waiter else ('kitchen' if s.is_kitchen else 'staff'))
        results.append({
            'staff_name': s.user.name if s.user_id else '',
            'restaurant_name': s.restaurant.name if s.restaurant_id else '',
            'role': role,
            'attendance_days': days,
            'per_day_salary': str(s.per_day_salary or 0),
            'to_pay': str(s.to_pay),
            'status': 'active' if not s.is_suspend else 'inactive',
        })
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_finance(request):
    """Finance report: revenue, expenses, dues, transactions summary; date range; owner scope."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_revenue': '0', 'total_due': '0', 'transaction_summary': {}, 'results': []})
    start_dt, end_dt = _parse_date_range(request)
    txn_qs = Transaction.objects.filter(restaurant_id__in=owner_ids)
    if start_dt and end_dt:
        txn_qs = txn_qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    total_revenue = txn_qs.filter(transaction_type=TransactionType.IN).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    total_due = Restaurant.objects.filter(id__in=owner_ids).aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    summary = {
        'total_transactions': txn_qs.count(),
        'total_revenue': str(total_revenue),
        'total_due': str(total_due),
    }
    return Response({**summary, 'results': []})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_credits(request):
    """Credits report: customer credits and restaurant due; owner scope."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'customer_credit_due': '0', 'restaurant_due': '0', 'results': []})
    customer_credit = CustomerRestaurant.objects.filter(restaurant_id__in=owner_ids).aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
    restaurant_due = Restaurant.objects.filter(id__in=owner_ids).aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    return Response({
        'customer_credit_due': str(customer_credit),
        'restaurant_due': str(restaurant_due),
        'results': [],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_customers(request):
    """Customer report: Customer, Orders, Spent, Credit, Tier; filters restaurant, date."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    start_dt, end_dt = _parse_date_range(request)
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid not in owner_ids:
                rid = None
        except ValueError:
            rid = None
    else:
        rid = None
    order_filter = Order.objects.filter(restaurant_id__in=owner_ids)
    if rid is not None:
        order_filter = order_filter.filter(restaurant_id=rid)
    if start_dt and end_dt:
        order_filter = order_filter.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    customer_ids = order_filter.values_list('customer_id', flat=True).distinct()
    customer_ids = [x for x in customer_ids if x is not None]
    if not customer_ids:
        return Response({'results': []})
    qs = Customer.objects.filter(id__in=customer_ids)
    results = []
    for c in qs:
        oq = Order.objects.filter(customer=c, restaurant_id__in=owner_ids)
        if rid is not None:
            oq = oq.filter(restaurant_id=rid)
        if start_dt and end_dt:
            oq = oq.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
        agg = oq.aggregate(orders=Count('id'), spent=Coalesce(Sum('total'), Value(Decimal('0'))))
        orders = agg['orders'] or 0
        spent = agg['spent'] or Decimal('0')
        credit = CustomerRestaurant.objects.filter(customer=c, restaurant_id__in=owner_ids).aggregate(s=Sum('to_pay'))['s'] or Decimal('0')
        tier = 'VIP' if orders >= 50 else ('Regular' if orders >= 20 else 'New')
        results.append({
            'customer_name': c.name,
            'customer_id': c.id,
            'orders': orders,
            'spent': str(spent),
            'credit': str(credit),
            'tier': tier,
        })
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_products(request):
    """Product report: product-wise sales quantity, revenue; filters restaurant, category, date."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    from .models import OrderItem, Product
    start_dt, end_dt = _parse_date_range(request)
    order_qs = Order.objects.filter(restaurant_id__in=owner_ids, payment_status__in=['paid', 'success'])
    if start_dt and end_dt:
        order_qs = order_qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    order_ids = list(order_qs.values_list('id', flat=True))
    if not order_ids:
        return Response({'results': []})
    items = OrderItem.objects.filter(order_id__in=order_ids).values('product_id', 'product__name').annotate(
        quantity=Count('id'),
        revenue=Sum('total'),
    )
    results = [{'product_id': r['product_id'], 'product_name': r['product__name'] or '', 'quantity': r['quantity'], 'revenue': str(r['revenue'] or 0)} for r in items]
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_inventory(request):
    """Inventory report: stock levels, low-stock; by restaurant, raw material; owner scope."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    try:
        from .models import RawMaterial
        qs = RawMaterial.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant').order_by('name')
        results = [{'id': r.id, 'name': r.name, 'restaurant_name': r.restaurant.name if r.restaurant_id else '', 'stock': str(getattr(r, 'stock', 0)), 'min_stock': str(getattr(r, 'min_stock', 0))} for r in qs]
    except Exception:
        results = []
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_pl(request):
    """P&L report: revenue, expenses breakdown, gross profit, net profit; monthly series; owner scope."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'revenue': '0', 'expenses': '0', 'net_profit': '0', 'breakdown': [], 'monthly': []})
    start_dt, end_dt = _parse_date_range(request)
    if not start_dt or not end_dt:
        from datetime import datetime
        now = timezone.now()
        start_dt = now - timedelta(days=365)
        end_dt = now
    txn_in = Transaction.objects.filter(restaurant_id__in=owner_ids, transaction_type=TransactionType.IN, created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    revenue = txn_in.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    order_revenue = Order.objects.filter(restaurant_id__in=owner_ids, payment_status__in=['paid', 'success'], created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date()).aggregate(s=Sum('total'))['s'] or Decimal('0')
    total_revenue = revenue + order_revenue
    staff_salaries = PaidRecord.objects.filter(restaurant_id__in=owner_ids, staff__isnull=False, created_at__gte=start_dt, created_at__lte=end_dt).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    vendor_pay = PaidRecord.objects.filter(restaurant_id__in=owner_ids, vendor__isnull=False, created_at__gte=start_dt, created_at__lte=end_dt).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    try:
        from .models import Expenses
        other_expenses = Expenses.objects.filter(restaurant_id__in=owner_ids, created_at__gte=start_dt, created_at__lte=end_dt).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    except Exception:
        other_expenses = Decimal('0')
    expenses = staff_salaries + vendor_pay + other_expenses
    net_profit = total_revenue - expenses
    breakdown = [
        {'label': 'Raw Material / Vendors', 'amount': str(vendor_pay)},
        {'label': 'Staff Salaries', 'amount': str(staff_salaries)},
        {'label': 'Operating Expenses', 'amount': str(other_expenses)},
    ]
    monthly = []
    return Response({
        'revenue': str(total_revenue),
        'expenses': str(expenses),
        'net_profit': str(net_profit),
        'breakdown': breakdown,
        'monthly': monthly,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSuperuser])
def restaurant_pay_due(request, pk):
    from .services import pay_due_balance
    try:
        rest = Restaurant.objects.get(pk=pk)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    amount = request.data.get('amount')
    if amount is None:
        return Response({'detail': 'amount required'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        pay_due_balance(rest, amount)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    rest.refresh_from_db()
    serializer = RestaurantDetailSerializer(rest, context={'request': request})
    return Response(serializer.data)


# ---------- KYC ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def kyc_list(request):
    qs = User.objects.filter(is_owner=True).order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(country_code__icontains=search)
        )
    status_filter = request.query_params.get('status')
    if status_filter in ('pending', 'approved', 'rejected'):
        qs = qs.filter(kyc_status=status_filter)
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = OwnerSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def kyc_stats(request):
    owners = User.objects.filter(is_owner=True)
    total = owners.count()
    from .models import KycStatus
    pending = owners.filter(kyc_status=KycStatus.PENDING).count()
    approved = owners.filter(kyc_status=KycStatus.APPROVED).count()
    rejected = owners.filter(kyc_status=KycStatus.REJECTED).count()
    return Response({
        'total_kyc': total,
        'pending_kyc': pending,
        'approved_kyc': approved,
        'rejected_kyc': rejected,
    })


# ---------- Shareholders ----------

def _shareholder_queryset(request):
    qs = User.objects.filter(is_shareholder=True).order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(country_code__icontains=search)
        )
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    return qs


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_list(request):
    if request.method == 'POST':
        serializer = OwnerCreateUpdateSerializer(
            data=request.data,
            context={'request': request, 'for_shareholder': True},
        )
        if serializer.is_valid():
            serializer.save()
            user = serializer.instance
            user.is_shareholder = True
            user.is_owner = False
            user.save(update_fields=['is_shareholder', 'is_owner'])
            return Response(OwnerSerializer(user, context={'request': request}).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = _shareholder_queryset(request)
    ordering = request.query_params.get('ordering') or request.query_params.get('sort') or '-created_at'
    allowed = ['created_at', '-created_at', 'name', '-name', 'balance', '-balance']
    if ordering.lstrip('-') in [f.lstrip('-') for f in allowed]:
        qs = qs.order_by(ordering)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    data = []
    for u in page:
        pending_w = ShareholderWithdrawal.objects.filter(user=u, status='pending').aggregate(s=Sum('amount'))['s'] or 0
        data.append({
            **OwnerSerializer(u, context={'request': request}).data,
            'pending_withdrawal_amount': str(pending_w),
        })
    return paginator.get_paginated_response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_search(request):
    phone = (request.query_params.get('phone') or '').strip()
    country_code = (request.query_params.get('country_code') or '').strip()
    if not phone:
        return Response({'detail': 'phone required'}, status=status.HTTP_400_BAD_REQUEST)
    qs = User.objects.filter(phone=phone)
    if country_code:
        qs = qs.filter(country_code=country_code)
    user = qs.first()
    if not user:
        return Response({'found': False, 'user': None})
    return Response({
        'found': True,
        'user': UserSerializer(user).data,
    })


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_detail(request, pk):
    try:
        user = User.objects.get(pk=pk, is_shareholder=True)
    except User.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method in ('PATCH', 'PUT'):
        serializer = OwnerCreateUpdateSerializer(user, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    if request.method == 'DELETE':
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    withdrawals = ShareholderWithdrawal.objects.filter(user=user).order_by('-created_at')
    serializer = OwnerSerializer(user, context={'request': request})
    data = serializer.data
    data['withdrawals'] = ShareholderWithdrawalSerializer(withdrawals, many=True).data
    pending_w = ShareholderWithdrawal.objects.filter(user=user, status='pending').aggregate(s=Sum('amount'))['s'] or 0
    data['pending_withdrawal_amount'] = str(pending_w)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_stats(request):
    shareholders = User.objects.filter(is_shareholder=True)
    total_sh = shareholders.count()
    sh_balance = shareholders.aggregate(s=Sum('balance'))['s'] or 0
    pending_w = ShareholderWithdrawal.objects.filter(status='pending').aggregate(s=Sum('amount'))['s'] or 0
    try:
        sys_setting = SuperSetting.objects.first()
        system_balance = sys_setting.balance if sys_setting else 0
    except Exception:
        system_balance = 0
    # Status counts for pie chart: Active / Inactive / Pending (mutually exclusive)
    active_sh = shareholders.filter(is_active=True, kyc_status=KycStatus.APPROVED).count()
    pending_sh = shareholders.filter(kyc_status=KycStatus.PENDING).count()
    inactive_sh = total_sh - active_sh - pending_sh
    status_distribution = [
        {'name': 'Active', 'value': active_sh},
        {'name': 'Inactive', 'value': inactive_sh},
        {'name': 'Pending', 'value': pending_sh},
    ]
    # Pie chart: share distribution (percentages per shareholder) - kept for backward compatibility
    dist = []
    for u in shareholders:
        dist.append({'name': u.name or str(u.phone), 'value': float(u.share_percentage or 0)})
    return Response({
        'total_shareholders': total_sh,
        'active_shareholders': active_sh,
        'inactive_shareholders': inactive_sh,
        'pending_shareholders': pending_sh,
        'status_distribution': status_distribution,
        'system_balance': str(system_balance),
        'shareholder_balance': str(sh_balance),
        'pending_withdrawal_balance': str(pending_w),
        'share_distribution': dist,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_analytics(request):
    start_dt, end_dt = _parse_date_range(request)
    # Earnings vs withdrawals from Transaction (share_distribution = distributed earnings, share_withdrawal = withdrawals)
    txn_qs = Transaction.objects.filter(category__in=[TransactionCategory.SHARE_DISTRIBUTION, TransactionCategory.SHARE_WITHDRAWAL])
    if start_dt is not None and end_dt is not None:
        txn_qs = txn_qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    by_date = txn_qs.annotate(date_key=TruncDate('created_at')).values('date_key', 'category').annotate(amount=Sum('amount')).order_by('date_key')
    from collections import defaultdict
    by_date_agg = defaultdict(lambda: {'distributed_earnings': Decimal('0'), 'withdrawals': Decimal('0')})
    for row in by_date:
        d = str(row['date_key']) if row['date_key'] else ''
        if row['category'] == TransactionCategory.SHARE_DISTRIBUTION:
            by_date_agg[d]['distributed_earnings'] += row['amount'] or Decimal('0')
        elif row['category'] == TransactionCategory.SHARE_WITHDRAWAL:
            by_date_agg[d]['withdrawals'] += row['amount'] or Decimal('0')
    earnings_vs_withdrawals = [{'date': k, 'distributed_earnings': float(v['distributed_earnings']), 'withdrawals': float(v['withdrawals'])} for k, v in sorted(by_date_agg.items())]
    # Monthly payout trend (share_distribution + share_withdrawal by month)
    monthly_qs = txn_qs.annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount_paid=Sum('amount')).order_by('month_key')
    monthly_payout_trend = []
    for m in monthly_qs:
        mk = m['month_key']
        month_str = mk.strftime('%Y-%m') if hasattr(mk, 'strftime') else str(mk)[:7]
        monthly_payout_trend.append({'month': month_str, 'amount_paid': float(m['amount_paid'] or 0)})
    return Response({
        'earnings_vs_withdrawals': earnings_vs_withdrawals,
        'monthly_payout_trend': monthly_payout_trend,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_withdrawal_history(request):
    user_id = request.query_params.get('user_id')
    if user_id:
        qs = ShareholderWithdrawal.objects.filter(user_id=user_id).order_by('-created_at')
    else:
        qs = ShareholderWithdrawal.objects.all().select_related('user').order_by('-created_at')
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ShareholderWithdrawalSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_withdrawal_stats(request):
    qs = ShareholderWithdrawal.objects.all()
    total_withdrawals = qs.count()
    pending_count = qs.filter(status=WithdrawalStatus.PENDING).count()
    approved_count = qs.filter(status=WithdrawalStatus.APPROVED).count()
    reject_count = qs.filter(status=WithdrawalStatus.REJECT).count()
    total_amount = qs.aggregate(s=Sum('amount'))['s'] or 0
    pending_amount = qs.filter(status=WithdrawalStatus.PENDING).aggregate(s=Sum('amount'))['s'] or 0
    approved_amount = qs.filter(status=WithdrawalStatus.APPROVED).aggregate(s=Sum('amount'))['s'] or 0
    failed_amount = qs.filter(status=WithdrawalStatus.REJECT).aggregate(s=Sum('amount'))['s'] or 0
    return Response({
        'total_withdrawals': total_withdrawals,
        'pending': pending_count,
        'approved': approved_count,
        'failed': reject_count,
        'total_amount': str(total_amount),
        'pending_amount': str(pending_amount),
        'approved_amount': str(approved_amount),
        'failed_amount': str(failed_amount),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_withdrawal_analytics(request):
    qs = ShareholderWithdrawal.objects.all()
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    status_qs = qs.values('status').annotate(count=Count('id')).order_by('-count')
    status_distribution = [{'status': s['status'], 'count': s['count']} for s in status_qs]
    request_trend_qs = qs.annotate(date_key=TruncDate('created_at')).values('date_key').annotate(count=Count('id')).order_by('date_key')
    request_trend = [{'date': str(r['date_key']), 'count': r['count']} for r in request_trend_qs]
    monthly_qs = qs.annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(total_amount=Sum('amount')).order_by('month_key')
    monthly_amount = []
    for row in monthly_qs:
        mk = row['month_key']
        month_str = mk.strftime('%Y-%m') if hasattr(mk, 'strftime') else str(mk)[:7]
        monthly_amount.append({'month': month_str, 'total_amount': float(row['total_amount'] or 0)})
    return Response({
        'status_distribution': status_distribution,
        'request_trend': request_trend,
        'monthly_amount': monthly_amount,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_withdrawal_list(request):
    if request.method == 'POST':
        serializer = ShareholderWithdrawalCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            w = serializer.instance
            out_serializer = ShareholderWithdrawalSerializer(w, context={'request': request})
            return Response(out_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user_id = request.query_params.get('user_id')
    if user_id:
        qs = ShareholderWithdrawal.objects.filter(user_id=user_id).select_related('user').order_by('-created_at')
    else:
        qs = ShareholderWithdrawal.objects.all().select_related('user').order_by('-created_at')
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ShareholderWithdrawalListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuser])
def shareholder_withdrawal_detail(request, pk):
    try:
        w = ShareholderWithdrawal.objects.select_related('user').get(pk=pk)
    except ShareholderWithdrawal.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = ShareholderWithdrawalDetailSerializer(w, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        data = request.data
        allowed = {'status', 'reject_reason'}
        payload = {k: data[k] for k in allowed if k in data}
        if not payload:
            return Response(ShareholderWithdrawalDetailSerializer(w, context={'request': request}).data)
        serializer = ShareholderWithdrawalSerializer(w, data=payload, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(ShareholderWithdrawalDetailSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# ---------- Transactions ----------

def _transaction_queryset(request):
    qs = Transaction.objects.select_related('restaurant', 'restaurant__user').order_by('-created_at')
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    txn_type = (request.query_params.get('transaction_type') or request.query_params.get('type') or '').strip().lower()
    if txn_type in ('in', 'out'):
        qs = qs.filter(transaction_type=txn_type)
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(remarks__icontains=search) |
            Q(payer_name__icontains=search) |
            Q(utr__icontains=search) |
            Q(restaurant__name__icontains=search) |
            Q(restaurant__slug__icontains=search)
        )
    return qs


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def transaction_stats(request):
    qs = Transaction.objects.all()
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    total_transaction = qs.count()
    total_revenue = qs.filter(transaction_type=TransactionType.IN).aggregate(s=Sum('amount'))['s'] or 0
    pending = qs.filter(payment_status=PaymentStatus.PENDING).count()
    success = qs.filter(payment_status__in=[PaymentStatus.SUCCESS, PaymentStatus.PAID]).count()
    failed = qs.exclude(payment_status__in=[PaymentStatus.PENDING, PaymentStatus.SUCCESS, PaymentStatus.PAID]).count()
    # Per-category counts (for IN transactions, as revenue components)
    subscription = qs.filter(category=TransactionCategory.SUBSCRIPTION_FEE).count()
    qr_stand_order = qs.filter(category=TransactionCategory.QR_STAND_ORDER).count()
    due_paid = qs.filter(category=TransactionCategory.DUE_PAID).count()
    share_distribution = qs.filter(category=TransactionCategory.SHARE_DISTRIBUTION).count()
    share_withdrawal = qs.filter(category=TransactionCategory.SHARE_WITHDRAWAL).count()
    transaction_fee = qs.filter(category=TransactionCategory.TRANSACTION_FEE).count()
    whatsapp_usage = qs.filter(category=TransactionCategory.WHATSAPP_USAGE).count()
    return Response({
        'total_transaction': total_transaction,
        'total_revenue': str(total_revenue),
        'pending': pending,
        'success': success,
        'failed': failed,
        'subscription': subscription,
        'qr_stand_order': qr_stand_order,
        'due': due_paid,
        'share_distribution': share_distribution,
        'withdrawals': share_withdrawal,
        'transaction_fee': transaction_fee,
        'whatsapp_usage': whatsapp_usage,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def transaction_list(request):
    qs = _transaction_queryset(request)
    ordering = request.query_params.get('ordering') or request.query_params.get('sort') or '-created_at'
    allowed = ['created_at', '-created_at', 'amount', '-amount']
    if ordering.lstrip('-') in [f.lstrip('-') for f in allowed]:
        qs = qs.order_by(ordering)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = TransactionSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def transaction_detail(request, pk):
    try:
        txn = Transaction.objects.select_related('restaurant', 'restaurant__user').get(pk=pk)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None and (txn.restaurant_id is None or txn.restaurant_id not in owner_ids):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = TransactionDetailSerializer(txn, context={'request': request})
    return Response(serializer.data)


# ---------- Super Settings (super admin) ----------

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSuperuser])
def super_setting_detail(request):
    """GET: return latest SuperSetting; PATCH: update it. Creates one if none exists (GET)."""
    from .services import get_super_setting
    ss = get_super_setting()
    if request.method == 'GET':
        serializer = SuperSettingSerializer(ss, context={'request': request})
        return Response(serializer.data)
    # PATCH
    serializer = SuperSettingUpdateSerializer(ss, data=request.data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        ss.refresh_from_db()
        return Response(SuperSettingSerializer(ss, context={'request': request}).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def super_settings_overview(request):
    """Live platform stats: users (total, owners, shareholders, kyc), restaurants (total, open, expired, with_due)."""
    from django.utils import timezone as tz
    today = tz.now().date()
    users_total = User.objects.count()
    users_owners = User.objects.filter(is_owner=True).count()
    users_shareholders = User.objects.filter(is_shareholder=True).count()
    users_kyc_pending = User.objects.filter(kyc_status=KycStatus.PENDING).count()
    users_kyc_rejected = User.objects.filter(kyc_status=KycStatus.REJECTED).count()
    rest_total = Restaurant.objects.count()
    rest_open = Restaurant.objects.filter(is_open=True).count()
    rest_expired = Restaurant.objects.filter(subscription_end__lt=today).count()
    rest_with_due = Restaurant.objects.filter(due_balance__gt=0).count()
    total_user_due = User.objects.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    return Response({
        'users': {
            'total': users_total,
            'owners': users_owners,
            'shareholders': users_shareholders,
            'kyc_pending': users_kyc_pending,
            'kyc_rejected': users_kyc_rejected,
        },
        'restaurants': {
            'total': rest_total,
            'open': rest_open,
            'subscription_expired': rest_expired,
            'with_due': rest_with_due,
        },
        'total_user_due': str(total_user_due),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def super_settings_dashboard_stats(request):
    """Single endpoint for dashboard: system balance, transactions, qr orders, revenue, users, restaurants, withdrawals, due_balances, notification_stats."""
    from .services import get_super_setting
    today = timezone.now().date()
    ss = get_super_setting()
    system_balance = ss.balance or Decimal('0')
    total_transactions = Transaction.objects.count()
    total_qr_stand_orders = QrStandOrder.objects.count()
    total_revenue = Transaction.objects.filter(
        transaction_type=TransactionType.IN,
        payment_status__in=[PaymentStatus.SUCCESS, PaymentStatus.PAID],
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    users_total = User.objects.count()
    users_owners = User.objects.filter(is_owner=True).count()
    users_shareholders = User.objects.filter(is_shareholder=True).count()
    users_kyc_pending = User.objects.filter(kyc_status=KycStatus.PENDING).count()
    rest_total = Restaurant.objects.count()
    rest_open = Restaurant.objects.filter(is_open=True).count()
    rest_expired = Restaurant.objects.filter(subscription_end__lt=today).count()
    rest_with_due = Restaurant.objects.filter(due_balance__gt=0).count()
    withdrawal_pending = ShareholderWithdrawal.objects.filter(status=WithdrawalStatus.PENDING).count()
    withdrawal_approved = ShareholderWithdrawal.objects.filter(status=WithdrawalStatus.APPROVED).count()
    total_user_due = User.objects.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    notif_total = BulkNotification.objects.count()
    notif_sms = BulkNotification.objects.filter(type='sms').count()
    notif_whatsapp = BulkNotification.objects.filter(type='whatsapp').count()
    return Response({
        'system_balance': str(system_balance),
        'total_transactions': total_transactions,
        'total_qr_stand_orders': total_qr_stand_orders,
        'total_revenue': str(total_revenue),
        'users': {
            'total': users_total,
            'owners': users_owners,
            'shareholders': users_shareholders,
            'kyc_pending': users_kyc_pending,
        },
        'restaurants': {
            'total': rest_total,
            'active': rest_open,
            'subscription_expired': rest_expired,
            'with_due': rest_with_due,
        },
        'withdrawals': {
            'pending': withdrawal_pending,
            'approved': withdrawal_approved,
        },
        'due_balances': str(total_user_due),
        'notification_stats': {
            'total': notif_total,
            'sms': notif_sms,
            'whatsapp': notif_whatsapp,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def super_settings_fee_income(request):
    """Fee income by category (transaction_fee, subscription_fee, qr_stand_order, whatsapp_usage) and monthly trend."""
    fee_categories = [
        TransactionCategory.TRANSACTION_FEE,
        TransactionCategory.SUBSCRIPTION_FEE,
        TransactionCategory.QR_STAND_ORDER,
        TransactionCategory.WHATSAPP_USAGE,
    ]
    qs = Transaction.objects.filter(
        transaction_type=TransactionType.IN,
        category__in=fee_categories,
    )
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    by_cat = qs.values('category').annotate(total=Sum('amount')).order_by('category')
    by_category = [{'category': r['category'], 'total': str(r['total'] or 0)} for r in by_cat]
    monthly_qs = qs.annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('amount')).order_by('month_key')
    monthly_trend = []
    for r in monthly_qs:
        mk = r['month_key']
        month_str = mk.strftime('%Y-%m') if hasattr(mk, 'strftime') else str(mk)[:7]
        monthly_trend.append({'month': month_str, 'amount': str(r['amount'] or 0)})
    return Response({
        'by_category': by_category,
        'monthly_trend': monthly_trend,
    })


# ---------- QR Stand Order ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_price(request):
    """Return per_qr_stand_price from SuperSetting for real-time total calculation in add form."""
    from .services import get_super_setting
    ss = get_super_setting()
    price = ss.per_qr_stand_price or 0
    return Response({'per_qr_stand_price': str(price)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_stats(request):
    qs = QrStandOrder.objects.all()
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    total_orders = qs.count()
    pending = qs.filter(status=QrStandOrderStatus.PENDING).count()
    accepted = qs.filter(status=QrStandOrderStatus.ACCEPTED).count()
    delivered = qs.filter(status__in=[QrStandOrderStatus.SHIPPED, QrStandOrderStatus.DELIVERED]).count()
    revenue_agg = qs.filter(payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]).aggregate(s=Sum('total'))
    total_revenue = revenue_agg['s'] or 0
    return Response({
        'total_orders': total_orders,
        'pending': pending,
        'accepted': accepted,
        'delivered': delivered,
        'total_revenue': str(total_revenue),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_list(request):
    if request.method == 'POST':
        serializer = QrStandOrderCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            order = serializer.instance
            out_serializer = QrStandOrderDetailSerializer(order, context={'request': request})
            return Response(out_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = QrStandOrder.objects.select_related('restaurant').order_by('-created_at')
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    status_filter = request.query_params.get('status', '').strip().lower()
    if status_filter in ('pending', 'accepted', 'shipped', 'delivered'):
        qs = qs.filter(status=status_filter)
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = QrStandOrderListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_detail(request, pk):
    try:
        order = QrStandOrder.objects.select_related('restaurant').get(pk=pk)
    except QrStandOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None and order.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = QrStandOrderDetailSerializer(order, context={'request': request})
        return Response(serializer.data)
    if request.method == 'DELETE':
        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method in ('PATCH', 'PUT'):
        data = request.data
        allowed = {'quantity', 'status'}
        payload = {k: data[k] for k in allowed if k in data}
        if not payload:
            return Response(QrStandOrderDetailSerializer(order, context={'request': request}).data)
        serializer = QrStandOrderUpdateSerializer(order, data=payload, partial=True)
        if serializer.is_valid():
            serializer.save()
            order.refresh_from_db()
            return Response(QrStandOrderDetailSerializer(order, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_pay(request, pk):
    from .services import pay_qr_stand_order
    try:
        order = QrStandOrder.objects.select_related('restaurant').get(pk=pk)
    except QrStandOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None and order.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        pay_qr_stand_order(order)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    order.refresh_from_db()
    serializer = QrStandOrderDetailSerializer(order, context={'request': request})
    return Response(serializer.data)


# ---------- QR Stand Order Analytics (reports) ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def qr_stand_order_analytics(request):
    qs = QrStandOrder.objects.all().select_related('restaurant')
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is not None and end_dt is not None:
        qs = qs.filter(created_at__date__gte=start_dt.date(), created_at__date__lte=end_dt.date())
    group_by = (request.query_params.get('group_by') or 'day').strip().lower()
    if group_by == 'month':
        date_expr = TruncMonth('created_at')
    else:
        date_expr = TruncDate('created_at')
    # Orders trend: by date, total + delivered + pending
    trend_qs = qs.annotate(date_key=date_expr).values('date_key').annotate(
        total_orders=Count('id'),
        delivered=Count('id', filter=Q(status__in=[QrStandOrderStatus.SHIPPED, QrStandOrderStatus.DELIVERED])),
        pending=Count('id', filter=Q(status=QrStandOrderStatus.PENDING)),
    ).order_by('date_key')
    def _date_str(obj):
        if obj is None:
            return ''
        if hasattr(obj, 'strftime'):
            return obj.strftime('%Y-%m-%d') if hasattr(obj, 'date') and callable(getattr(obj, 'date')) else obj.strftime('%Y-%m-%d')
        return str(obj)[:10]

    orders_trend = [
        {'date': _date_str(t['date_key']), 'total_orders': t['total_orders'], 'delivered': t['delivered'], 'pending': t['pending']}
        for t in trend_qs
    ]
    # Revenue trend
    rev_qs = qs.filter(payment_status__in=[PaymentStatus.PAID, PaymentStatus.SUCCESS]).annotate(date_key=date_expr).values('date_key').annotate(revenue=Sum('total')).order_by('date_key')
    revenue_trend = [
        {'date': _date_str(r['date_key']), 'revenue': float(r['revenue'] or 0)}
        for r in rev_qs
    ]
    # Order status distribution
    status_qs = qs.values('status').annotate(count=Count('id')).order_by('-count')
    order_status_distribution = [{'status': s['status'], 'count': s['count']} for s in status_qs]
    # Restaurant-wise orders
    rest_qs = qs.values('restaurant__name').annotate(count=Count('id')).order_by('-count')
    restaurant_orders = [{'restaurant_name': r['restaurant__name'] or '—', 'count': r['count']} for r in rest_qs]
    return Response({
        'orders_trend': orders_trend,
        'revenue_trend': revenue_trend,
        'order_status_distribution': order_status_distribution,
        'restaurant_orders': restaurant_orders,
    })


# ---------- Notifications (super admin) ----------

def _notification_data(request):
    """Build data dict for create/update; parse receivers from JSON string if form data."""
    data = dict(request.data) if hasattr(request.data, 'items') else {}
    if request.FILES and 'image' in request.FILES:
        data['image'] = request.FILES['image']
    receivers = data.get('receivers')
    if isinstance(receivers, str):
        import json
        try:
            data['receivers'] = json.loads(receivers)
        except Exception:
            data['receivers'] = []
    return data


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def notification_list(request):
    if request.method == 'POST':
        data = _notification_data(request)
        serializer = BulkNotificationCreateUpdateSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            obj = serializer.save()
            obj.total_count = len(obj.receivers or [])
            obj.sent_count = 0
            obj.save(update_fields=['total_count', 'sent_count'])
            return Response(
                BulkNotificationDetailSerializer(obj, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = BulkNotification.objects.select_related('restaurant').order_by('-created_at')
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(message__icontains=search)
    type_filter = (request.query_params.get('type') or '').strip().lower()
    if type_filter in ('sms', 'whatsapp'):
        qs = qs.filter(type=type_filter)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = BulkNotificationListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def notification_detail(request, pk):
    try:
        obj = BulkNotification.objects.select_related('restaurant').get(pk=pk)
    except BulkNotification.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None and obj.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = BulkNotificationDetailSerializer(obj, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        data = _notification_data(request)
        serializer = BulkNotificationCreateUpdateSerializer(obj, data=data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            obj.refresh_from_db()
            obj.total_count = len(obj.receivers or [])
            obj.save(update_fields=['total_count'])
            return Response(BulkNotificationDetailSerializer(obj, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def notification_send(request, pk):
    try:
        obj = BulkNotification.objects.select_related('restaurant').get(pk=pk)
    except BulkNotification.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None and obj.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    total = len(obj.receivers or [])
    if total == 0:
        return Response({'detail': 'No receivers.'}, status=status.HTTP_400_BAD_REQUEST)
    obj.sent_count = total
    obj.save(update_fields=['sent_count'])
    serializer = BulkNotificationDetailSerializer(obj, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def notification_stats(request):
    """Return total, sms, whatsapp counts for BulkNotification."""
    qs = BulkNotification.objects.all()
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    total = qs.count()
    sms = qs.filter(type='sms').count()
    whatsapp = qs.filter(type='whatsapp').count()
    return Response({
        'total': total,
        'sms': sms,
        'whatsapp': whatsapp,
    })


# ---------- Customers (super admin, for receiver picker) ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def customer_list(request):
    qs = Customer.objects.all().order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(country_code__icontains=search)
        )
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = CustomerListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)
