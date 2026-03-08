import json
from django.db.models import Q, Sum, Count, F, Avg
from django.db.models.functions import Coalesce
from django.db.models import Value
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import datetime, timedelta, time
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
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
    OrderItem,
    CustomerRestaurant,
    Attendance,
    PaidRecord,
    ReceivedRecord,
    AttendanceStatus,
    Unit,
    Category,
    Table,
    RawMaterial,
    Product,
    ProductVariant,
    ComboSet,
    Purchase,
    PurchaseItem,
    Feedback,
    Expenses,
)
from .models import PaymentStatus, DiscountType, OrderType
from .permissions import IsSuperuser, IsSuperuserOrOwner
from .serializers import (
    _build_media_url,
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
    AttendanceListSerializer,
    AttendanceUpdateSerializer,
    FeedbackListSerializer,
    FeedbackDetailSerializer,
    OwnerVendorListSerializer,
    OwnerVendorCreateUpdateSerializer,
    UnitListSerializer,
    UnitCreateUpdateSerializer,
    CategoryListSerializer,
    CategoryCreateUpdateSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ComboSetListSerializer,
    ComboSetDetailSerializer,
    ComboSetCreateUpdateSerializer,
    ExpenseListSerializer,
    ExpenseDetailSerializer,
    ExpenseCreateUpdateSerializer,
)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _owner_restaurant_ids(request):
    """Return list of restaurant IDs for request.user when owner; else None (no filter)."""
    if getattr(request.user, 'is_owner', False):
        return list(Restaurant.objects.filter(user=request.user).values_list('id', flat=True))
    return None


def _manager_restaurant_id(request):
    """Return single restaurant_id when request.user is restaurant staff (e.g. manager); else None."""
    if not getattr(request.user, 'is_restaurant_staff', False):
        return None
    staff = Staff.objects.filter(user=request.user).first()
    return staff.restaurant_id if staff else None


def _current_staff(request):
    """Return Staff instance for request.user when they are restaurant staff; else None."""
    if not getattr(request.user, 'is_restaurant_staff', False):
        return None
    return Staff.objects.filter(user=request.user).select_related('user', 'restaurant').first()


def _owner_or_manager_restaurant_ids(request):
    """Return list of restaurant IDs for owner (all their restaurants) or manager (single restaurant); else None."""
    owner_ids = _owner_restaurant_ids(request)
    if owner_ids is not None:
        return owner_ids
    manager_rid = _manager_restaurant_id(request)
    if manager_rid is not None:
        return [manager_rid]
    return None


def _parse_date_range(request):
    """Return (start_dt, end_dt) from query params: range preset or start_date/end_date."""
    range_preset = (request.query_params.get('range') or '').strip().lower()
    now = timezone.now()
    if range_preset in ('last_24h', 'last_24_hour', 'today'):
        return now - timedelta(hours=24), now
    if range_preset == 'yesterday':
        yesterday_date = now.date() - timedelta(days=1)
        start_dt = timezone.make_aware(datetime.combine(yesterday_date, time.min))
        end_dt = timezone.make_aware(datetime.combine(yesterday_date, time.max))
        return start_dt, end_dt
    if range_preset == 'week':
        return now - timedelta(days=7), now
    if range_preset == 'month':
        return now - timedelta(days=30), now
    if range_preset == 'monthly':
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start_dt, now
    if range_preset == 'yearly':
        start_dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start_dt, now
    start_s = request.query_params.get('start_date')
    end_s = request.query_params.get('end_date')
    if start_s and end_s:
        try:
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
        owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    """Owner-scoped dashboard: restaurants count, staff count, revenue, due, recent activity. Waiter gets own stats."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    current_staff = _current_staff(request)
    if current_staff is not None and current_staff.is_waiter:
        # Waiter dashboard: my orders today, pending, recent orders, my attendance today, restaurant info
        today = timezone.now().date()
        my_orders_today = Order.objects.filter(
            restaurant_id__in=owner_ids,
            waiter_id=current_staff.id,
            created_at__date=today,
        ).count()
        pending_orders = Order.objects.filter(
            restaurant_id__in=owner_ids,
            waiter_id=current_staff.id,
        ).exclude(payment_status__in=['paid', 'success'])
        pending_count = pending_orders.count()
        recent_orders_qs = Order.objects.filter(
            restaurant_id__in=owner_ids,
            waiter_id=current_staff.id,
            created_at__date=today,
        ).annotate(items_count=Count('items')).select_related('table').order_by('-created_at')[:15]
        recent_orders = [
            {
                'id': o.id,
                'table_number': o.table_number or (o.table.name if o.table_id else ''),
                'total': str(o.total),
                'status': o.status,
                'payment_status': o.payment_status,
                'items_count': getattr(o, 'items_count', 0),
                'created_at': o.created_at.isoformat() if hasattr(o.created_at, 'isoformat') else str(o.created_at),
            }
            for o in recent_orders_qs
        ]
        my_attendance_today = Attendance.objects.filter(
            staff_id=current_staff.id,
            date=today,
        ).first()
        attendance_status = my_attendance_today.status if my_attendance_today else 'unmarked'
        # My orders by day (last 7 days) for line chart
        my_orders_by_day = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cnt = Order.objects.filter(
                restaurant_id__in=owner_ids,
                waiter_id=current_staff.id,
                created_at__date=d,
            ).count()
            my_orders_by_day.append({'date': d.isoformat(), 'count': cnt})
        single_rest = Restaurant.objects.filter(id=owner_ids[0]).first() if owner_ids else None
        payload = {
            'my_orders_today': my_orders_today,
            'pending_orders_count': pending_count,
            'recent_orders': recent_orders,
            'attendance_today_status': attendance_status,
            'restaurant_id': owner_ids[0] if len(owner_ids) == 1 else None,
            'my_orders_by_day': my_orders_by_day,
        }
        if single_rest:
            from .serializers import _build_media_url
            logo_url = None
            if single_rest.logo:
                logo_url = _build_media_url(request, single_rest.logo.url if hasattr(single_rest.logo, 'url') else str(single_rest.logo))
            payload['restaurant_slug'] = single_rest.slug
            payload['restaurant_name'] = single_rest.name
            payload['restaurant_logo_url'] = logo_url
        return Response(payload)
    start_dt, end_dt = _parse_date_range(request)
    qs_rest = Restaurant.objects.filter(id__in=owner_ids)
    restaurants_count = qs_rest.count()
    active_restaurants = qs_rest.filter(is_open=True).count()
    total_due = qs_rest.aggregate(s=Sum('due_balance'))['s'] or Decimal('0')
    staff_count = Staff.objects.filter(restaurant_id__in=owner_ids).count()

    if start_dt is not None and end_dt is not None:
        txn_revenue = Transaction.objects.filter(
            restaurant_id__in=owner_ids,
            transaction_type=TransactionType.IN,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        order_revenue = Order.objects.filter(
            restaurant_id__in=owner_ids,
            payment_status__in=['paid', 'success'],
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).aggregate(s=Sum('total'))['s'] or Decimal('0')
        total_revenue = txn_revenue + order_revenue
        order_count = Order.objects.filter(
            restaurant_id__in=owner_ids,
            payment_status__in=['paid', 'success'],
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).count()
        recent = Transaction.objects.filter(
            restaurant_id__in=owner_ids,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).order_by('-created_at')[:10]
    else:
        total_revenue = qs_rest.aggregate(s=Sum('balance'))['s'] or Decimal('0')
        order_count = None
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
    # Orders by day (last 7 days) for line chart (owner/manager/kitchen)
    today = timezone.now().date()
    orders_by_day = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        cnt = Order.objects.filter(restaurant_id__in=owner_ids, created_at__date=d).count()
        orders_by_day.append({'date': d.isoformat(), 'count': cnt})
    total_orders_all_time = Order.objects.filter(restaurant_id__in=owner_ids).count()
    payload = {
        'restaurants_count': restaurants_count,
        'staff_count': staff_count,
        'total_revenue': str(total_revenue),
        'total_due': str(total_due),
        'active_restaurants': active_restaurants,
        'recent_transactions': recent_data,
        'orders_by_day': orders_by_day,
        'total_orders_all_time': total_orders_all_time,
    }
    if order_count is not None:
        payload['order_count'] = order_count

    # Manager dashboard extras when date range is provided
    if start_dt is not None and end_dt is not None:
        pending_orders_count = Order.objects.filter(
            restaurant_id__in=owner_ids,
        ).exclude(payment_status__in=['paid', 'success']).count()
        payload['pending_orders_count'] = pending_orders_count

        low_stock_qs = RawMaterial.objects.filter(
            restaurant_id__in=owner_ids,
            min_stock__isnull=False,
        ).filter(stock__lt=F('min_stock'))
        payload['low_stock_count'] = low_stock_qs.count()
        payload['low_stock_items'] = [
            {
                'id': r.id,
                'name': r.name,
                'stock': str(r.stock),
                'min_stock': str(r.min_stock),
                'unit': r.unit.symbol or r.unit.name if r.unit_id else '',
            }
            for r in low_stock_qs.select_related('unit')[:20]
        ]

        payload['active_tables_count'] = Table.objects.filter(restaurant_id__in=owner_ids).count()

        recent_orders_qs = Order.objects.filter(
            restaurant_id__in=owner_ids,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).annotate(items_count=Count('items')).select_related('table').order_by('-created_at')[:15]
        payload['recent_orders'] = [
            {
                'id': o.id,
                'table_number': o.table_number or (o.table.name if o.table_id else ''),
                'total': str(o.total),
                'status': o.status,
                'payment_status': o.payment_status,
                'items_count': getattr(o, 'items_count', 0),
                'created_at': o.created_at.isoformat() if hasattr(o.created_at, 'isoformat') else str(o.created_at),
            }
            for o in recent_orders_qs
        ]

        today = timezone.now().date()
        attendance_today_qs = Attendance.objects.filter(
            restaurant_id__in=owner_ids,
            date=today,
        ).select_related('staff', 'staff__user').order_by('staff__user__name')
        payload['attendance_today'] = [
            {
                'staff_name': a.staff.user.name if a.staff and a.staff.user_id else '',
                'status': a.status,
            }
            for a in attendance_today_qs
        ]

        # Customers count (distinct customers with orders at these restaurants)
        customers_count = Customer.objects.filter(
            orders__restaurant_id__in=owner_ids,
        ).exclude(user__is_restaurant_staff=True).distinct().count()
        payload['customers_count'] = customers_count

        # Single restaurant: include slug, name, logo for manager dashboard / Menu QR
        if len(owner_ids) == 1:
            single_rest = Restaurant.objects.filter(id=owner_ids[0]).first()
            if single_rest:
                from .serializers import _build_media_url
                logo_url = None
                if single_rest.logo:
                    logo_url = _build_media_url(request, single_rest.logo.url if hasattr(single_rest.logo, 'url') else str(single_rest.logo))
                payload['restaurant_slug'] = single_rest.slug
                payload['restaurant_name'] = single_rest.name
                payload['restaurant_logo_url'] = logo_url

    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_my_restaurant(request):
    """Return current manager's restaurant (id, slug, name, logo_url). For staff with single restaurant only."""
    manager_rid = _manager_restaurant_id(request)
    if manager_rid is None:
        return Response({'detail': 'Not available.'}, status=status.HTTP_404_NOT_FOUND)
    rest = Restaurant.objects.filter(id=manager_rid).first()
    if not rest:
        return Response({'detail': 'Restaurant not found.'}, status=status.HTTP_404_NOT_FOUND)
    from .serializers import _build_media_url
    logo_url = None
    if rest.logo:
        logo_url = _build_media_url(request, rest.logo.url if hasattr(rest.logo, 'url') else str(rest.logo))
    return Response({
        'id': rest.id,
        'slug': rest.slug,
        'name': rest.name,
        'logo_url': logo_url,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_available_users(request):
    """List users that can be assigned as staff. Search by phone required. Excludes only users already staff at the given restaurant (or at any of owner's restaurants if no restaurant_id)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'results': []})
    search = (request.query_params.get('search') or '').strip()
    if not search:
        return Response({'results': []})
    restaurant_id_param = request.query_params.get('restaurant_id')
    if restaurant_id_param is not None:
        try:
            restaurant_id = int(restaurant_id_param)
        except (TypeError, ValueError):
            restaurant_id = None
    else:
        restaurant_id = None
    if restaurant_id is not None and restaurant_id in owner_ids:
        already_staff_user_ids = list(Staff.objects.filter(restaurant_id=restaurant_id).values_list('user_id', flat=True))
    else:
        already_staff_user_ids = list(Staff.objects.filter(restaurant_id__in=owner_ids).values_list('user_id', flat=True).distinct())
    qs = User.objects.exclude(is_superuser=True).order_by('name', 'phone')
    if already_staff_user_ids:
        qs = qs.exclude(id__in=already_staff_user_ids)
    qs = qs.filter(phone__icontains=search)[:100]
    results = [{'id': u.id, 'name': u.name or '', 'phone': u.phone or ''} for u in qs]
    return Response({'results': results})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_staff_list(request):
    """List staff for owner's restaurants; search, pagination, filter active/inactive. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        serializer = OwnerStaffCreateUpdateSerializer(
            data=request.data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                OwnerStaffListSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Staff.objects.filter(restaurant_id__in=owner_ids).select_related('user', 'restaurant').prefetch_related('assigned_tables').order_by('restaurant__name', 'user__name')
    include_attendance_days = request.query_params.get('include_attendance_days', '').strip() == '1'
    start_date_param = request.query_params.get('start_date', '').strip()
    end_date_param = request.query_params.get('end_date', '').strip()
    if include_attendance_days and start_date_param and end_date_param:
        try:
            start_dt = datetime.strptime(start_date_param, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date_param, '%Y-%m-%d').date()
            if start_dt <= end_dt:
                qs = qs.annotate(
                    attendance_days=Count(
                        'attendances',
                        filter=Q(
                            attendances__status=AttendanceStatus.PRESENT,
                            attendances__date__gte=start_dt,
                            attendances__date__lte=end_dt,
                        ),
                    ),
                )
        except (ValueError, TypeError):
            pass
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        staff = Staff.objects.select_related('user', 'restaurant').prefetch_related('assigned_tables').get(pk=pk)
    except Staff.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if staff.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = OwnerStaffListSerializer(staff, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = OwnerStaffCreateUpdateSerializer(
            staff, data=request.data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerStaffListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# --- Attendance (owner/manager) ---

def _owner_attendance_list_for_date(owner_ids, restaurant_id, att_date):
    staff_list = list(Staff.objects.filter(restaurant_id=restaurant_id).select_related('user').order_by('user__name'))
    attendance_by_staff = {
        a.staff_id: a
        for a in Attendance.objects.filter(restaurant_id=restaurant_id, date=att_date).select_related('staff', 'staff__user')
    }
    results = []
    for s in staff_list:
        att = attendance_by_staff.get(s.id)
        if att:
            results.append({
                'id': att.id,
                'staff_id': s.id,
                'staff_name': s.user.name or '',
                'status': att.status.lower(),
                'leave_reason': att.leave_reason or '',
                'created_at': att.created_at.isoformat() if att.created_at else None,
            })
        else:
            results.append({
                'id': None,
                'staff_id': s.id,
                'staff_name': s.user.name or '',
                'status': 'unmarked',
                'leave_reason': '',
                'created_at': None,
            })
    present = sum(1 for r in results if r['status'] == 'present')
    absent = sum(1 for r in results if r['status'] == 'absent')
    leave = sum(1 for r in results if r['status'] == 'leave')
    return {'results': results, 'stats': {'present': present, 'absent': absent, 'leave': leave, 'total_staff': len(results)}}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_attendance_list(request):
    """GET: list attendance for a restaurant on a given date. POST: create attendance record (for unmarked staff)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'results': [], 'stats': {'present': 0, 'absent': 0, 'leave': 0, 'total_staff': 0}})
    if request.method == 'POST':
        rid = request.data.get('restaurant_id')
        sid = request.data.get('staff_id')
        date_param = request.data.get('date')
        if rid is None or sid is None or not date_param:
            return Response({'detail': 'restaurant_id, staff_id and date required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rid = int(rid)
            sid = int(sid)
            att_date = datetime.strptime(str(date_param).strip()[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({'detail': 'Invalid restaurant_id, staff_id or date.'}, status=status.HTTP_400_BAD_REQUEST)
        if rid not in owner_ids:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        staff = Staff.objects.filter(restaurant_id=rid, id=sid).first()
        if not staff:
            return Response({'detail': 'Staff not found.'}, status=status.HTTP_404_NOT_FOUND)
        status_val = (request.data.get('status') or 'absent').strip().lower()
        if status_val not in ('present', 'absent', 'leave'):
            status_val = 'absent'
        leave_reason = (request.data.get('leave_reason') or '').strip()
        if status_val == 'leave' and not leave_reason:
            return Response(
                {'leave_reason': ['Leave reason is required when status is leave.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        att, created = Attendance.objects.get_or_create(
            restaurant_id=rid, staff=staff, date=att_date,
            defaults={
                'status': status_val,
                'leave_reason': leave_reason,
                'created_by': request.user,
            },
        )
        if not created:
            att.status = status_val
            att.leave_reason = leave_reason
            att.created_by = request.user
            att.save()
        return Response({
            'id': att.id,
            'staff_id': att.staff_id,
            'staff_name': att.staff.user.name or '',
            'status': att.status,
            'leave_reason': att.leave_reason or '',
            'created_at': att.created_at.isoformat() if att.created_at else None,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    restaurant_id_param = request.query_params.get('restaurant_id', '').strip()
    date_param = request.query_params.get('date', '').strip()
    if not date_param:
        return Response({'detail': 'date (YYYY-MM-DD) required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        att_date = datetime.strptime(date_param, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
    restaurant_id = int(restaurant_id_param) if restaurant_id_param else (owner_ids[0] if len(owner_ids) == 1 else None)
    if restaurant_id is None or restaurant_id not in owner_ids:
        return Response({'detail': 'Valid restaurant_id required.'}, status=status.HTTP_400_BAD_REQUEST)
    out = _owner_attendance_list_for_date(owner_ids, restaurant_id, att_date)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        out['results'] = [r for r in out['results'] if r['staff_id'] == current_staff.id]
        out['stats'] = {
            'present': sum(1 for r in out['results'] if r['status'] == 'present'),
            'absent': sum(1 for r in out['results'] if r['status'] == 'absent'),
            'leave': sum(1 for r in out['results'] if r['status'] == 'leave'),
            'total_staff': len(out['results']),
        }
    return Response(out)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_attendance_stats(request):
    """Stats for attendance on a given date: present, absent, leave, total_staff."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'present': 0, 'absent': 0, 'leave': 0, 'total_staff': 0})
    restaurant_id_param = request.query_params.get('restaurant_id', '').strip()
    date_param = request.query_params.get('date', '').strip()
    if not date_param:
        return Response({'detail': 'date (YYYY-MM-DD) required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        att_date = datetime.strptime(date_param, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'detail': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    restaurant_id = int(restaurant_id_param) if restaurant_id_param else owner_ids[0]
    if restaurant_id not in owner_ids:
        return Response({'present': 0, 'absent': 0, 'leave': 0, 'total_staff': 0})
    total_staff = Staff.objects.filter(restaurant_id=restaurant_id).count()
    agg = Attendance.objects.filter(restaurant_id=restaurant_id, date=att_date).values('status').annotate(c=Count('id'))
    counts = {r['status'].lower(): r['c'] for r in agg}
    return Response({
        'present': counts.get('present', 0),
        'absent': counts.get('absent', 0),
        'leave': counts.get('leave', 0),
        'total_staff': total_staff,
    })


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_attendance_detail(request, pk):
    """Get or update a single attendance record by id."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        att = Attendance.objects.select_related('staff', 'staff__user').get(pk=pk)
    except Attendance.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if att.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager and att.staff_id != current_staff.id:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response({
            'id': att.id,
            'staff_id': att.staff_id,
            'staff_name': att.staff.user.name or '',
            'status': att.status,
            'leave_reason': att.leave_reason or '',
            'created_at': att.created_at.isoformat() if att.created_at else None,
        })
    if request.method in ('PATCH', 'PUT'):
        if current_staff is not None and not current_staff.is_manager:
            return Response({'detail': 'Waiter cannot edit attendance.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = AttendanceUpdateSerializer(att, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            att.created_by = request.user
            att.save(update_fields=['created_by'])
            att.refresh_from_db()
            return Response({
                'id': att.id,
                'staff_id': att.staff_id,
                'staff_name': att.staff.user.name or '',
                'status': att.status,
                'leave_reason': att.leave_reason or '',
                'created_at': att.created_at.isoformat() if att.created_at else None,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_attendance_my_list(request):
    """List current staff's own attendance in date range (for waiter/kitchen). from_date, to_date required (YYYY-MM-DD)."""
    current_staff = _current_staff(request)
    if current_staff is None or current_staff.is_manager:
        return Response({'detail': 'Not available.'}, status=status.HTTP_403_FORBIDDEN)
    from_param = (request.query_params.get('from_date') or request.query_params.get('from') or '').strip()
    to_param = (request.query_params.get('to_date') or request.query_params.get('to') or '').strip()
    if not from_param or not to_param:
        return Response({'detail': 'from_date and to_date (YYYY-MM-DD) required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        from_date = datetime.strptime(from_param[:10], '%Y-%m-%d').date()
        to_date = datetime.strptime(to_param[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return Response({'detail': 'Invalid date format.'}, status=status.HTTP_400_BAD_REQUEST)
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    qs = Attendance.objects.filter(
        staff_id=current_staff.id,
        date__gte=from_date,
        date__lte=to_date,
    ).order_by('-date')
    results = [
        {
            'id': a.id,
            'date': a.date.isoformat(),
            'status': a.status.lower(),
            'leave_reason': a.leave_reason or '',
            'created_at': a.created_at.isoformat() if a.created_at else None,
        }
        for a in qs
    ]
    present = sum(1 for r in results if r['status'] == 'present')
    absent = sum(1 for r in results if r['status'] == 'absent')
    leave = sum(1 for r in results if r['status'] == 'leave')
    return Response({
        'results': results,
        'stats': {'present': present, 'absent': absent, 'leave': leave, 'total_days': len(results)},
    })


# --- Feedback (owner/manager) ---

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_feedback_list(request):
    """List feedback for owner/manager restaurants. Optional restaurant_id, pagination."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    restaurant_id_param = request.query_params.get('restaurant_id', '').strip()
    restaurant_id = int(restaurant_id_param) if restaurant_id_param else (owner_ids[0] if len(owner_ids) == 1 else None)
    if restaurant_id is None or restaurant_id not in owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    qs = Feedback.objects.filter(restaurant_id=restaurant_id).select_related('customer', 'order').order_by('-created_at')
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = FeedbackListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_feedback_stats(request):
    """Feedback stats: average_rating, total_count, count_by_rating (1-5)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'average_rating': 0, 'total_count': 0, 'count_by_rating': {str(i): 0 for i in range(1, 6)}})
    restaurant_id_param = request.query_params.get('restaurant_id', '').strip()
    restaurant_id = int(restaurant_id_param) if restaurant_id_param else owner_ids[0]
    if restaurant_id not in owner_ids:
        return Response({'average_rating': 0, 'total_count': 0, 'count_by_rating': {str(i): 0 for i in range(1, 6)}})
    qs = Feedback.objects.filter(restaurant_id=restaurant_id)
    total = qs.count()
    avg = qs.aggregate(a=Avg('rating'))['a']
    average_rating = round(float(avg or 0), 1)
    by_rating = dict(qs.values('rating').annotate(c=Count('id')).values_list('rating', 'c'))
    count_by_rating = {str(i): by_rating.get(i, 0) for i in range(1, 6)}
    return Response({'average_rating': average_rating, 'total_count': total, 'count_by_rating': count_by_rating})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_feedback_detail(request, pk):
    """Get a single feedback by id."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        fb = Feedback.objects.select_related('customer', 'order').get(pk=pk)
    except Feedback.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if fb.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = FeedbackDetailSerializer(fb, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_customers_list(request):
    """List customers with orders in owner's restaurants; total_orders, total_spent, credit_due."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    qs = Customer.objects.filter(orders__restaurant_id__in=owner_ids).exclude(
        user__is_restaurant_staff=True
    ).distinct().annotate(
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total': 0, 'vip_count': 0, 'credit_due': '0'})
    qs = Customer.objects.filter(orders__restaurant_id__in=owner_ids).exclude(
        user__is_restaurant_staff=True
    ).distinct().annotate(
        order_count=Count('orders'),
        total_spent=Coalesce(Sum('orders__total'), Value(Decimal('0'))),
    )
    total = qs.count()
    vip_count = sum(1 for c in qs if getattr(c, 'order_count', 0) >= 50)
    credit_agg = CustomerRestaurant.objects.filter(
        restaurant_id__in=owner_ids
    ).exclude(customer__user__is_restaurant_staff=True).aggregate(s=Sum('to_pay'))
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        serializer = OwnerVendorCreateUpdateSerializer(
            data=request.data,
            context={'request': request, 'owner_ids': owner_ids},
        )
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
        serializer = OwnerVendorCreateUpdateSerializer(
            vendor, data=request.data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(OwnerVendorListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_vendors_stats(request):
    """Total vendors, sum to_pay, sum to_receive for owner's restaurants."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
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


# --- Units (owner/manager scoped) ---

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def units_list(request):
    """List units for owner/manager restaurants. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not data.get('restaurant') and len(owner_ids) == 1:
            data['restaurant'] = owner_ids[0]
        serializer = UnitCreateUpdateSerializer(
            data=data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                UnitListSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Unit.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant').order_by('name')
    serializer = UnitListSerializer(qs, many=True, context={'request': request})
    return Response({'results': serializer.data})


@api_view(['GET', 'PATCH', 'PUT'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def unit_detail(request, pk):
    """Get or update a single unit."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        unit = Unit.objects.select_related('restaurant').get(pk=pk)
    except Unit.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if unit.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = UnitListSerializer(unit, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = UnitCreateUpdateSerializer(
            unit, data=request.data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UnitListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# --- Categories (owner/manager scoped) ---

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def categories_list(request):
    """List categories for owner/manager restaurants with item_count. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        if not data.get('restaurant') and len(owner_ids) == 1:
            data['restaurant'] = owner_ids[0]
        serializer = CategoryCreateUpdateSerializer(
            data=data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                CategoryListSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    from .models import Product
    qs = Category.objects.filter(restaurant_id__in=owner_ids).annotate(
        item_count=Count('products', distinct=True),
    ).select_related('restaurant').order_by('name')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(name__icontains=search)
    serializer = CategoryListSerializer(qs, many=True, context={'request': request})
    return Response({'results': serializer.data})


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def category_detail(request, pk):
    """Get, update, or delete a single category."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        category = Category.objects.select_related('restaurant').get(pk=pk)
    except Category.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if category.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'GET':
        from .models import Product
        category_with_count = Category.objects.filter(pk=pk, restaurant_id__in=owner_ids).annotate(
            item_count=Count('products', distinct=True),
        ).select_related('restaurant').first()
        if not category_with_count:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategoryListSerializer(category_with_count, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        serializer = CategoryCreateUpdateSerializer(
            category, data=data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(CategoryListSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# --- Raw materials (owner/manager scoped) ---

def _raw_material_to_dict(r, request=None):
    from .serializers import _build_media_url
    image_url = None
    if getattr(r, 'image', None) and r.image and request:
        image_url = _build_media_url(request, r.image.url if hasattr(r.image, 'url') else str(r.image))
    return {
        'id': r.id,
        'name': r.name,
        'restaurant_id': r.restaurant_id,
        'restaurant_name': r.restaurant.name if r.restaurant_id else '',
        'unit_id': r.unit_id,
        'unit_name': r.unit.name if r.unit_id else '',
        'unit_symbol': r.unit.symbol if r.unit_id else '',
        'stock': str(r.stock),
        'min_stock': str(r.min_stock) if r.min_stock is not None else None,
        'price': str(r.price),
        'image_url': image_url,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def raw_materials_list(request):
    """List raw materials for owner/manager restaurants. Optional low_stock=true, restaurant_id=. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        restaurant_id = data.get('restaurant')
        if not restaurant_id and len(owner_ids) == 1:
            restaurant_id = owner_ids[0]
        if not restaurant_id or int(restaurant_id) not in owner_ids:
            return Response({'detail': 'Valid restaurant is required.'}, status=status.HTTP_400_BAD_REQUEST)
        unit_id = data.get('unit')
        if not unit_id:
            return Response({'detail': 'Unit is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if Unit.objects.filter(pk=unit_id, restaurant_id=restaurant_id).exists() is False:
            return Response({'detail': 'Unit must belong to the restaurant.'}, status=status.HTTP_400_BAD_REQUEST)
        name = (data.get('name') or '').strip()
        if not name:
            return Response({'detail': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        min_stock = data.get('min_stock')
        stock = data.get('stock', 0)
        price = data.get('price', 0)
        try:
            min_stock = Decimal(str(min_stock)) if min_stock is not None and str(min_stock).strip() != '' else None
        except Exception:
            min_stock = None
        try:
            stock = Decimal(str(stock)) if stock is not None else Decimal('0')
        except Exception:
            stock = Decimal('0')
        try:
            price = Decimal(str(price)) if price is not None else Decimal('0')
        except Exception:
            price = Decimal('0')
        vendor_id = data.get('vendor')
        if vendor_id is not None and str(vendor_id).strip() != '':
            try:
                vid = int(vendor_id)
                if Vendor.objects.filter(pk=vid, restaurant_id=restaurant_id).exists() is False:
                    vendor_id = None
            except (TypeError, ValueError):
                vendor_id = None
        else:
            vendor_id = None
        image_file = request.FILES.get('image') if request.FILES else None
        raw = RawMaterial.objects.create(
            name=name,
            restaurant_id=restaurant_id,
            unit_id=unit_id,
            min_stock=min_stock,
            stock=stock,
            price=price,
            vendor_id=vendor_id or None,
            image=image_file,
        )
        raw.refresh_from_db()
        raw = RawMaterial.objects.select_related('restaurant', 'unit').get(pk=raw.id)
        return Response(_raw_material_to_dict(raw, request), status=status.HTTP_201_CREATED)
    qs = RawMaterial.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant', 'unit').order_by('name')
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    if request.query_params.get('low_stock') == 'true':
        qs = qs.filter(min_stock__isnull=False).filter(stock__lt=F('min_stock'))
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(name__icontains=search)
    results = [_raw_material_to_dict(r, request) for r in qs]
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def raw_materials_stats(request):
    """Stats for raw materials: total_items, low_stock_count, out_of_stock_count, total_value. Optional restaurant_id=."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_items': 0, 'low_stock_count': 0, 'out_of_stock_count': 0, 'total_value': '0'})
    qs = RawMaterial.objects.filter(restaurant_id__in=owner_ids)
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    total_items = qs.count()
    low_stock_count = qs.filter(min_stock__isnull=False).filter(stock__lt=F('min_stock')).count()
    out_of_stock_count = qs.filter(stock__lte=0).count()
    total_value_qs = qs.annotate(line_value=F('stock') * F('price')).aggregate(s=Sum('line_value'))
    total_value = total_value_qs['s'] or Decimal('0')
    return Response({
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_value': str(total_value),
    })


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def raw_material_detail(request, pk):
    """Get, update, or delete a single raw material. Scope by owner/manager restaurants."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        r = RawMaterial.objects.select_related('restaurant', 'unit').get(pk=pk)
    except RawMaterial.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if r.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        r.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'PATCH':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES and 'image' in request.FILES:
            r.image = request.FILES['image']
        if 'name' in data and data['name'] is not None:
            name = (data.get('name') or '').strip()
            if name:
                r.name = name
        if 'unit_id' in data or 'unit' in data:
            unit_id = data.get('unit_id') or data.get('unit')
            if unit_id is not None:
                if Unit.objects.filter(pk=unit_id, restaurant_id=r.restaurant_id).exists():
                    r.unit_id = unit_id
        if 'min_stock' in data:
            try:
                v = data['min_stock']
                r.min_stock = Decimal(str(v)) if v is not None and str(v).strip() != '' else None
            except Exception:
                pass
        if 'stock' in data:
            try:
                r.stock = Decimal(str(data['stock']))
            except Exception:
                pass
        if 'price' in data:
            try:
                r.price = Decimal(str(data['price']))
            except Exception:
                pass
        r.save()
        r.refresh_from_db()
        r = RawMaterial.objects.select_related('restaurant', 'unit').get(pk=r.id)
    return Response(_raw_material_to_dict(r, request))


# --- Tables (owner/manager scoped) ---

def _table_status_and_order(table_id):
    """Return (status, current_order_id) for table. status: available | occupied. reserved not modeled -> available."""
    active = Order.objects.filter(
        table_id=table_id
    ).exclude(status__in=('served', 'rejected')).order_by('-created_at').first()
    if active:
        return ('occupied', active.id)
    return ('available', None)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def tables_list(request):
    """List tables for owner/manager restaurants. POST to create. Each row includes status and current_order_id."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        current_staff = _current_staff(request)
        if current_staff is not None and not current_staff.is_manager:
            return Response({'detail': 'Waiter cannot create tables.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        restaurant_id = data.get('restaurant')
        if not restaurant_id and len(owner_ids) == 1:
            restaurant_id = owner_ids[0]
        if not restaurant_id or int(restaurant_id) not in owner_ids:
            return Response({'detail': 'Valid restaurant is required.'}, status=status.HTTP_400_BAD_REQUEST)
        name = (data.get('name') or '').strip()
        if not name:
            return Response({'detail': 'Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            capacity = int(data.get('capacity', 0) or 0)
        except (TypeError, ValueError):
            capacity = 0
        floor = (data.get('floor') or '').strip() or ''
        near_by = (data.get('near_by') or '').strip() or ''
        notes = (data.get('notes') or '').strip() or ''
        image_file = request.FILES.get('image') if request.FILES else None
        tbl = Table.objects.create(
            restaurant_id=restaurant_id,
            name=name,
            capacity=capacity,
            floor=floor,
            near_by=near_by,
            notes=notes,
            image=image_file,
        )
        status_str, order_id = _table_status_and_order(tbl.id)
        from .serializers import _build_media_url
        image_url = None
        if tbl.image:
            image_url = _build_media_url(request, tbl.image.url if hasattr(tbl.image, 'url') else str(tbl.image))
        return Response({
            'id': tbl.id,
            'name': tbl.name,
            'capacity': tbl.capacity,
            'floor': tbl.floor or '',
            'near_by': tbl.near_by or '',
            'restaurant_id': tbl.restaurant_id,
            'status': status_str,
            'current_order_id': order_id,
            'image_url': image_url,
        }, status=status.HTTP_201_CREATED)
    qs = Table.objects.filter(restaurant_id__in=owner_ids).order_by('floor', 'name')
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    from .serializers import _build_media_url
    results = []
    for t in qs:
        status_str, order_id = _table_status_and_order(t.id)
        image_url = None
        if t.image:
            image_url = _build_media_url(request, t.image.url if hasattr(t.image, 'url') else str(t.image))
        results.append({
            'id': t.id,
            'name': t.name,
            'capacity': t.capacity,
            'floor': t.floor or '',
            'near_by': t.near_by or '',
            'restaurant_id': t.restaurant_id,
            'status': status_str,
            'current_order_id': order_id,
            'image_url': image_url,
        })
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def tables_stats(request):
    """Total tables, available, occupied, reserved (reserved=0 if not modeled). Optional restaurant_id=."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total': 0, 'available': 0, 'occupied': 0, 'reserved': 0})
    qs = Table.objects.filter(restaurant_id__in=owner_ids)
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    total = qs.count()
    occupied_ids = set(
        Order.objects.filter(
            table_id__in=qs.values_list('id', flat=True)
        ).exclude(status__in=('served', 'rejected')).values_list('table_id', flat=True).distinct()
    )
    occupied = len(occupied_ids)
    available = total - occupied
    return Response({'total': total, 'available': available, 'occupied': occupied, 'reserved': 0})


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def table_detail(request, pk):
    """Get, update, or delete a single table. Scope by owner/manager restaurants. GET includes status and current_order_id."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        t = Table.objects.get(pk=pk)
    except Table.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if t.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager and request.method in ('PATCH', 'PUT', 'DELETE'):
        return Response({'detail': 'Waiter cannot edit or delete tables.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'DELETE':
        t.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'PATCH':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES and 'image' in request.FILES:
            t.image = request.FILES['image']
        if 'name' in data and data['name'] is not None:
            name = (data.get('name') or '').strip()
            if name:
                t.name = name
        if 'capacity' in data:
            try:
                t.capacity = int(data.get('capacity', 0) or 0)
            except (TypeError, ValueError):
                pass
        if 'floor' in data:
            t.floor = (data.get('floor') or '').strip() or ''
        if 'near_by' in data:
            t.near_by = (data.get('near_by') or '').strip() or ''
        if 'notes' in data:
            t.notes = (data.get('notes') or '').strip() or ''
        t.save()
    status_str, order_id = _table_status_and_order(t.id)
    from .serializers import _build_media_url
    image_url = None
    if t.image:
        image_url = _build_media_url(request, t.image.url if hasattr(t.image, 'url') else str(t.image))
    return Response({
        'id': t.id,
        'name': t.name,
        'capacity': t.capacity,
        'floor': t.floor or '',
        'near_by': t.near_by or '',
        'restaurant_id': t.restaurant_id,
        'status': status_str,
        'current_order_id': order_id,
        'image_url': image_url,
    })


# --- Purchases (owner/manager scoped) ---

def _purchase_to_dict(p, items=None):
    """Build purchase response dict. If items not provided, fetch from p.items."""
    if items is None:
        items = list(p.items.select_related('raw_material').all())
    item_list = [
        {
            'id': i.id,
            'raw_material_id': i.raw_material_id,
            'raw_material_name': i.raw_material.name if i.raw_material_id else '',
            'quantity': str(i.quantity),
            'price': str(i.price),
            'total': str(i.total),
        }
        for i in items
    ]
    return {
        'id': p.id,
        'restaurant_id': p.restaurant_id,
        'vendor_id': p.vendor_id,
        'vendor_name': p.vendor.name if getattr(p, 'vendor', None) and p.vendor_id else '',
        'subtotal': str(p.subtotal),
        'discount_type': p.discount_type or '',
        'discount': str(p.discount),
        'total': str(p.total),
        'created_at': p.created_at.isoformat() if hasattr(p.created_at, 'isoformat') else str(p.created_at),
        'items_count': len(item_list),
        'items': item_list,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def purchases_list(request):
    """List purchases for owner/manager restaurants. POST to create with nested items. Optional start_date, end_date, restaurant_id."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': [], 'stats': {'total_count': 0, 'total_amount': '0', 'total_subtotal': '0'}})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        restaurant_id = data.get('restaurant')
        if not restaurant_id and len(owner_ids) == 1:
            restaurant_id = owner_ids[0]
        if not restaurant_id or int(restaurant_id) not in owner_ids:
            return Response({'detail': 'Valid restaurant is required.'}, status=status.HTTP_400_BAD_REQUEST)
        items_data = data.get('items') or []
        if not items_data:
            return Response({'detail': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)
        vendor_id = data.get('vendor') or data.get('vendor_id')
        if vendor_id is not None:
            try:
                vid = int(vendor_id)
                if Vendor.objects.filter(pk=vid, restaurant_id=restaurant_id).exists() is False:
                    vendor_id = None
            except (TypeError, ValueError):
                vendor_id = None
        else:
            vendor_id = None
        discount_type = (data.get('discount_type') or '').strip() or ''
        try:
            discount = Decimal(str(data.get('discount') or 0))
        except Exception:
            discount = Decimal('0')
        raw_ids_ok = set(
            RawMaterial.objects.filter(restaurant_id=restaurant_id).values_list('id', flat=True)
        )
        subtotal = Decimal('0')
        purchase = Purchase.objects.create(
            restaurant_id=restaurant_id,
            vendor_id=vendor_id or None,
            discount_type=discount_type or None,
            discount=discount,
            subtotal=Decimal('0'),
            total=Decimal('0'),
        )
        created_items = []
        for row in items_data:
            rm_id = row.get('raw_material_id') or row.get('raw_material')
            if rm_id not in raw_ids_ok:
                continue
            try:
                qty = Decimal(str(row.get('quantity') or 0))
                price = Decimal(str(row.get('price') or 0))
            except Exception:
                continue
            if qty <= 0:
                continue
            item_total = qty * price
            subtotal += item_total
            pi = PurchaseItem.objects.create(
                purchase=purchase,
                raw_material_id=rm_id,
                quantity=qty,
                price=price,
                total=item_total,
            )
            created_items.append(pi)
        if not created_items:
            purchase.delete()
            return Response({'detail': 'At least one valid item is required.'}, status=status.HTTP_400_BAD_REQUEST)
        purchase.subtotal = subtotal
        if discount_type == 'flat':
            purchase.total = max(Decimal('0'), subtotal - discount)
        elif discount_type == 'percentage':
            purchase.total = subtotal * (Decimal('100') - discount) / Decimal('100')
        else:
            purchase.total = subtotal
        purchase.save()
        purchase.refresh_from_db()
        purchase = Purchase.objects.select_related('vendor').get(pk=purchase.id)
        return Response(_purchase_to_dict(purchase, created_items), status=status.HTTP_201_CREATED)
    qs = Purchase.objects.filter(restaurant_id__in=owner_ids).select_related('vendor').annotate(
        items_count=Count('items'),
    ).order_by('-created_at')
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    results = [
        {
            'id': p.id,
            'restaurant_id': p.restaurant_id,
            'vendor_id': p.vendor_id,
            'vendor_name': p.vendor.name if p.vendor_id and getattr(p, 'vendor', None) else '',
            'subtotal': str(p.subtotal),
            'discount_type': p.discount_type or '',
            'discount': str(p.discount),
            'total': str(p.total),
            'created_at': p.created_at.isoformat() if hasattr(p.created_at, 'isoformat') else str(p.created_at),
            'items_count': getattr(p, 'items_count', p.items.count()),
        }
        for p in qs
    ]
    stats_qs = Purchase.objects.filter(restaurant_id__in=owner_ids)
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                stats_qs = stats_qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    if start_date:
        try:
            stats_qs = stats_qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    if end_date:
        try:
            stats_qs = stats_qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    agg = stats_qs.aggregate(total_amount=Sum('total'), total_subtotal=Sum('subtotal'))
    return Response({
        'results': results,
        'stats': {
            'total_count': stats_qs.count(),
            'total_amount': str(agg['total_amount'] or 0),
            'total_subtotal': str(agg['total_subtotal'] or 0),
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def purchases_stats(request):
    """Purchase stats for period. Optional restaurant_id, start_date, end_date."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_count': 0, 'total_amount': '0', 'total_subtotal': '0'})
    qs = Purchase.objects.filter(restaurant_id__in=owner_ids)
    restaurant_id = request.query_params.get('restaurant_id')
    if restaurant_id:
        try:
            rid = int(restaurant_id)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except (TypeError, ValueError):
            pass
    for param, key in [('start_date', 'created_at__date__gte'), ('end_date', 'created_at__date__lte')]:
        val = request.query_params.get(param, '').strip()[:10]
        if val:
            try:
                qs = qs.filter(**{key: val})
            except Exception:
                pass
    agg = qs.aggregate(total_amount=Sum('total'), total_subtotal=Sum('subtotal'))
    return Response({
        'total_count': qs.count(),
        'total_amount': str(agg['total_amount'] or 0),
        'total_subtotal': str(agg['total_subtotal'] or 0),
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def purchase_detail(request, pk):
    """Get or update a single purchase. Scope by owner/manager restaurants. PATCH can update header and replace items."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        p = Purchase.objects.select_related('vendor', 'restaurant').get(pk=pk)
    except Purchase.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if p.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'PATCH':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'vendor' in data or 'vendor_id' in data:
            vid = data.get('vendor') or data.get('vendor_id')
            if vid is not None and str(vid).strip() != '':
                try:
                    if Vendor.objects.filter(pk=int(vid), restaurant_id=p.restaurant_id).exists():
                        p.vendor_id = int(vid)
                except (TypeError, ValueError):
                    pass
            else:
                p.vendor_id = None
        if 'discount_type' in data:
            p.discount_type = (data.get('discount_type') or '').strip() or ''
        if 'discount' in data:
            try:
                p.discount = Decimal(str(data['discount']))
            except Exception:
                pass
        if 'items' in data:
            items_data = data.get('items') or []
            p.items.all().delete()
            raw_ids_ok = set(
                RawMaterial.objects.filter(restaurant_id=p.restaurant_id).values_list('id', flat=True)
            )
            subtotal = Decimal('0')
            for row in items_data:
                rm_id = row.get('raw_material_id') or row.get('raw_material')
                if rm_id not in raw_ids_ok:
                    continue
                try:
                    qty = Decimal(str(row.get('quantity') or 0))
                    price = Decimal(str(row.get('price') or 0))
                except Exception:
                    continue
                if qty <= 0:
                    continue
                item_total = qty * price
                subtotal += item_total
                PurchaseItem.objects.create(
                    purchase=p,
                    raw_material_id=rm_id,
                    quantity=qty,
                    price=price,
                    total=item_total,
                )
            p.subtotal = subtotal
            # Purchase.save() will set p.total from compute_total()
        else:
            p.save()
        p.save()
        p.refresh_from_db()
        p = Purchase.objects.select_related('vendor').get(pk=p.id)
    return Response(_purchase_to_dict(p))


# --- Orders list (owner/manager scoped) ---

def _order_create_response(order, request):
    """Build order detail dict for order_detail and order create response."""
    items = []
    subtotal = Decimal('0')
    for item in order.items.all():
        line_total = item.total
        subtotal += line_total
        items.append({
            'id': item.id,
            'name': _order_item_name(item),
            'quantity': str(item.quantity),
            'price': str(item.price),
            'total': str(line_total),
            'image_url': _order_item_image_url(item, request),
        })
    return {
        'id': order.id,
        'restaurant_id': order.restaurant_id,
        'table_id': order.table_id,
        'table_number': order.table_number or (order.table.name if order.table_id else ''),
        'order_type': order.order_type,
        'status': order.status,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method or '',
        'waiter_id': order.waiter_id,
        'waiter_name': order.waiter.user.name if order.waiter and order.waiter.user_id else '',
        'subtotal': str(subtotal),
        'service_charge': str(order.service_charge) if order.service_charge is not None else None,
        'discount': str(order.discount) if order.discount is not None else None,
        'total': str(order.total),
        'created_at': order.created_at.isoformat() if hasattr(order.created_at, 'isoformat') else str(order.created_at),
        'updated_at': order.updated_at.isoformat() if hasattr(order.updated_at, 'isoformat') else str(order.updated_at),
        'items': items,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def orders_list(request):
    """List orders for owner/manager restaurants. POST to create. Filters: status, payment_status, start_date, end_date. Paginated."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        restaurant_id = data.get('restaurant')
        if not restaurant_id and len(owner_ids) == 1:
            restaurant_id = owner_ids[0]
        try:
            restaurant_id = int(restaurant_id)
        except (TypeError, ValueError):
            return Response({'detail': 'Valid restaurant is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if restaurant_id not in owner_ids:
            return Response({'detail': 'Restaurant not in your scope.'}, status=status.HTTP_403_FORBIDDEN)
        restaurant = Restaurant.objects.filter(pk=restaurant_id).first()
        order_type = (data.get('order_type') or 'table').strip().lower()
        if order_type not in (OrderType.TABLE, OrderType.PACKING, OrderType.DELIVERY):
            order_type = OrderType.TABLE
        items_data = data.get('items') or []
        if not items_data:
            return Response({'detail': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)
        table_id = data.get('table_id')
        if table_id is not None:
            try:
                table_id = int(table_id)
                if Table.objects.filter(pk=table_id, restaurant_id=restaurant_id).exists() is False:
                    table_id = None
            except (TypeError, ValueError):
                table_id = None
        else:
            table_id = None
        table_number = (data.get('table_number') or '').strip() or None
        address = (data.get('address') or '').strip() or None
        sent_charge = data.get('service_charge')
        if sent_charge is not None and sent_charge != '':
            try:
                service_charge = Decimal(str(sent_charge))
            except Exception:
                service_charge = getattr(restaurant, 'default_service_charge', None) or Decimal('0')
        else:
            service_charge = getattr(restaurant, 'default_service_charge', None) or Decimal('0')
        payment_method = (data.get('payment_method') or '').strip() or None
        if payment_method and payment_method not in ('cash', 'e_wallet', 'bank'):
            payment_method = None
        waiter_id = data.get('waiter_id')
        if waiter_id is not None:
            try:
                waiter_id = int(waiter_id)
                if Staff.objects.filter(pk=waiter_id, restaurant_id=restaurant_id).exists() is False:
                    waiter_id = None
            except (TypeError, ValueError):
                waiter_id = None
        else:
            waiter_id = None
        order_total = Decimal('0')
        line_items = []
        for row in items_data:
            qty = Decimal(str(row.get('quantity') or 1))
            if qty <= 0:
                continue
            pv_id = row.get('product_variant_id')
            prod_id = row.get('product_id')
            combo_id = row.get('combo_set_id')
            unit_price = None
            product_variant_id = None
            product_id = None
            combo_set_id = None
            if pv_id:
                try:
                    pv = ProductVariant.objects.select_related('product').get(
                        pk=pv_id, product__restaurant_id=restaurant_id
                    )
                    unit_price = pv.get_final_price()
                    product_variant_id = pv.id
                    product_id = pv.product_id
                except (ProductVariant.DoesNotExist, TypeError, ValueError):
                    pass
            if unit_price is None and prod_id:
                try:
                    prod = Product.objects.filter(pk=prod_id, restaurant_id=restaurant_id).first()
                    if prod:
                        first_v = prod.variants.first()
                        if first_v:
                            unit_price = first_v.get_final_price()
                            product_variant_id = first_v.id
                            product_id = prod.id
                except Exception:
                    pass
            if unit_price is None and combo_id:
                try:
                    combo = ComboSet.objects.get(pk=combo_id, restaurant_id=restaurant_id)
                    unit_price = combo.price
                    combo_set_id = combo.id
                except (ComboSet.DoesNotExist, TypeError, ValueError):
                    pass
            if unit_price is not None and (product_variant_id or product_id or combo_set_id):
                line_total = unit_price * qty
                order_total += line_total
                line_items.append({
                    'product_id': product_id,
                    'product_variant_id': product_variant_id,
                    'combo_set_id': combo_set_id,
                    'price': unit_price,
                    'quantity': qty,
                    'total': line_total,
                })
        if not line_items:
            return Response({'detail': 'No valid items.'}, status=status.HTTP_400_BAD_REQUEST)
        order_total += service_charge
        order = Order.objects.create(
            restaurant_id=restaurant_id,
            table_id=table_id,
            table_number=table_number,
            order_type=order_type,
            address=address,
            status='pending',
            payment_status='pending',
            payment_method=payment_method or '',
            waiter_id=waiter_id,
            total=order_total,
            service_charge=service_charge if service_charge else None,
        )
        for line in line_items:
            OrderItem.objects.create(
                order=order,
                product_id=line.get('product_id'),
                product_variant_id=line.get('product_variant_id'),
                combo_set_id=line.get('combo_set_id'),
                price=line['price'],
                quantity=line['quantity'],
                total=line['total'],
            )
        order.refresh_from_db()
        order = Order.objects.select_related('table', 'waiter', 'waiter__user').prefetch_related(
            'items__product', 'items__product_variant', 'items__product_variant__product', 'items__combo_set'
        ).get(pk=order.id)
        return Response(_order_create_response(order, request), status=status.HTTP_201_CREATED)
    qs = Order.objects.filter(restaurant_id__in=owner_ids).annotate(
        items_count=Count('items'),
        total_quantity=Coalesce(Sum('items__quantity'), Value(Decimal('0'))),
    ).select_related('table', 'waiter', 'waiter__user').order_by('-created_at')
    current_staff = _current_staff(request)
    # Kitchen sees all restaurant orders; waiter sees only their own
    if current_staff is not None and not current_staff.is_manager and not getattr(current_staff, 'is_kitchen', False):
        qs = qs.filter(waiter_id=current_staff.id)
    status_param = request.query_params.get('status', '').strip()
    if status_param:
        qs = qs.filter(status=status_param)
    payment_status_param = request.query_params.get('payment_status', '').strip()
    if payment_status_param:
        qs = qs.filter(payment_status=payment_status_param)
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = [
        {
            'id': o.id,
            'restaurant_id': o.restaurant_id,
            'table_id': o.table_id,
            'table_number': o.table_number or (o.table.name if o.table_id else ''),
            'order_type': o.order_type,
            'total': str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'items_count': getattr(o, 'items_count', 0),
            'service_charge': str(o.service_charge) if o.service_charge is not None else None,
            'total_quantity': str(getattr(o, 'total_quantity', 0)),
            'waiter_id': o.waiter_id,
            'waiter_name': o.waiter.user.name if o.waiter and o.waiter.user_id else '',
            'created_at': o.created_at.isoformat() if hasattr(o.created_at, 'isoformat') else str(o.created_at),
        }
        for o in page
    ]
    return paginator.get_paginated_response(results)


def _order_item_name(item):
    """Return display name for an OrderItem (product, combo, or variant)."""
    if item.product_id:
        return item.product.name if item.product else f'Product #{item.product_id}'
    if item.combo_set_id:
        return item.combo_set.name if item.combo_set else f'Combo #{item.combo_set_id}'
    if item.product_variant_id and item.product_variant:
        p = item.product_variant.product_id
        base = item.product_variant.product.name if p and getattr(item.product_variant, 'product', None) else f'Variant #{item.product_variant_id}'
        return base
    return 'Item'


def _order_item_image_url(item, request):
    """Return image URL for an OrderItem from product, variant's product, or combo_set."""
    image_field = None
    if item.product_id and item.product and getattr(item.product, 'image', None) and item.product.image:
        image_field = item.product.image
    elif item.product_variant_id and item.product_variant:
        prod = getattr(item.product_variant, 'product', None)
        if prod and getattr(prod, 'image', None) and prod.image:
            image_field = prod.image
    elif item.combo_set_id and item.combo_set and getattr(item.combo_set, 'image', None) and item.combo_set.image:
        image_field = item.combo_set.image
    if not image_field:
        return None
    url = image_field.url if hasattr(image_field, 'url') else str(image_field)
    return _build_media_url(request, url)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def order_detail(request, pk):
    """Get or update a single order. PATCH allows status and payment_status."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        order = Order.objects.filter(restaurant_id__in=owner_ids).select_related(
            'table', 'waiter', 'waiter__user'
        ).prefetch_related('items__product', 'items__product_variant', 'items__product_variant__product', 'items__combo_set').get(pk=pk)
    except Order.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    current_staff = _current_staff(request)
    # Kitchen can access any order in restaurant; waiter only their own
    if current_staff is not None and not current_staff.is_manager and not getattr(current_staff, 'is_kitchen', False) and order.waiter_id != current_staff.id:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'PATCH':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        allowed = {}
        is_kitchen = current_staff is not None and getattr(current_staff, 'is_kitchen', False)
        if 'status' in data and data['status']:
            new_status = data['status'].strip().lower()
            if is_kitchen and new_status not in ('accepted', 'running', 'ready', 'served'):
                pass  # Kitchen can only set these statuses
            else:
                allowed['status'] = new_status
        if not is_kitchen and 'payment_status' in data and data['payment_status']:
            allowed['payment_status'] = data['payment_status'].strip()
        if allowed:
            Order.objects.filter(pk=pk).update(**allowed)
            order.refresh_from_db()
    # Build detail response
    items = []
    subtotal = Decimal('0')
    for item in order.items.all():
        line_total = item.total
        subtotal += line_total
        items.append({
            'id': item.id,
            'name': _order_item_name(item),
            'quantity': str(item.quantity),
            'price': str(item.price),
            'total': str(line_total),
            'image_url': _order_item_image_url(item, request),
        })
    return Response({
        'id': order.id,
        'restaurant_id': order.restaurant_id,
        'table_id': order.table_id,
        'table_number': order.table_number or (order.table.name if order.table_id else ''),
        'order_type': order.order_type,
        'status': order.status,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method or '',
        'waiter_id': order.waiter_id,
        'waiter_name': order.waiter.user.name if order.waiter and order.waiter.user_id else '',
        'subtotal': str(subtotal),
        'service_charge': str(order.service_charge) if order.service_charge is not None else None,
        'discount': str(order.discount) if order.discount is not None else None,
        'total': str(order.total),
        'created_at': order.created_at.isoformat() if hasattr(order.created_at, 'isoformat') else str(order.created_at),
        'updated_at': order.updated_at.isoformat() if hasattr(order.updated_at, 'isoformat') else str(order.updated_at),
        'items': items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def orders_stats(request):
    """Stats for listing/dashboard: today_orders_count, pending_count, revenue_today, by_status."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({
            'today_orders_count': 0,
            'pending_count': 0,
            'revenue_today': '0',
            'by_status': {},
        })
    today = timezone.now().date()
    qs = Order.objects.filter(restaurant_id__in=owner_ids)
    current_staff = _current_staff(request)
    # Kitchen sees all restaurant orders; waiter sees only their own
    if current_staff is not None and not current_staff.is_manager and not getattr(current_staff, 'is_kitchen', False):
        qs = qs.filter(waiter_id=current_staff.id)
    today_qs = qs.filter(created_at__date=today)
    today_orders_count = today_qs.count()
    pending_count = qs.filter(status='pending').count()
    revenue_today = today_qs.filter(payment_status='paid').aggregate(s=Sum('total'))['s'] or Decimal('0')
    by_status = dict(qs.values('status').annotate(c=Count('id')).values_list('status', 'c'))
    orders_by_day = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        cnt = qs.filter(created_at__date=d).count()
        orders_by_day.append({'date': d.isoformat(), 'count': cnt})
    return Response({
        'today_orders_count': today_orders_count,
        'pending_count': pending_count,
        'revenue_today': str(revenue_today),
        'by_status': by_status,
        'orders_by_day': orders_by_day,
    })


# --- Expenses (owner/manager scoped) ---

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def expenses_list(request):
    """List or create expenses. GET: optional restaurant, start_date, end_date. POST: create (restaurant from body or single allowed)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if not data.get('restaurant') and len(owner_ids) == 1:
            data['restaurant'] = owner_ids[0]
        if data.get('restaurant') and int(data.get('restaurant')) not in owner_ids:
            return Response({'detail': 'Restaurant not in your scope.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExpenseCreateUpdateSerializer(
            data=data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                ExpenseDetailSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Expenses.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant', 'vendor').order_by('-created_at')
    restaurant_param = request.query_params.get('restaurant', '').strip()
    if restaurant_param:
        try:
            rid = int(restaurant_param)
            if rid in owner_ids:
                qs = qs.filter(restaurant_id=rid)
        except ValueError:
            pass
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = ExpenseListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def expense_detail(request, pk):
    """Get or update a single expense."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        expense = Expenses.objects.select_related('restaurant', 'vendor').get(pk=pk, restaurant_id__in=owner_ids)
    except Expenses.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'PATCH':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        serializer = ExpenseCreateUpdateSerializer(
            expense, data=data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(ExpenseDetailSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    serializer = ExpenseDetailSerializer(expense, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def expenses_stats(request):
    """Total amount and count for period; optional by_category (aggregate by name)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_amount': '0', 'count': 0, 'by_category': []})
    qs = Expenses.objects.filter(restaurant_id__in=owner_ids)
    start_date = request.query_params.get('start_date', '').strip()[:10]
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    agg = qs.aggregate(total=Sum('amount'), count=Count('id'))
    by_category = list(
        qs.values('name').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')
    )
    return Response({
        'total_amount': str(agg['total'] or 0),
        'count': agg['count'] or 0,
        'by_category': [{'category': b['name'], 'total': str(b['total']), 'count': b['count']} for b in by_category],
    })


# --- Products (owner/manager scoped) ---

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def products_list(request):
    """List products for owner/manager restaurants. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        variants_raw = data.get('variants')
        if request.POST.get('variants') is not None and (variants_raw is None or variants_raw == ''):
            variants_raw = request.POST.get('variants')
        if isinstance(variants_raw, str):
            try:
                data['variants'] = json.loads(variants_raw)
            except Exception:
                data['variants'] = []
        elif not isinstance(data.get('variants'), list):
            data['variants'] = []
        raw_links_raw = data.get('raw_material_links')
        if request.POST.get('raw_material_links') is not None and (raw_links_raw is None or raw_links_raw == ''):
            raw_links_raw = request.POST.get('raw_material_links')
        if isinstance(raw_links_raw, str):
            try:
                data['raw_material_links'] = json.loads(raw_links_raw)
            except Exception:
                data['raw_material_links'] = []
        elif not isinstance(data.get('raw_material_links'), list):
            data['raw_material_links'] = []
        if not data.get('restaurant') and len(owner_ids) == 1:
            data['restaurant'] = owner_ids[0]
        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            product = Product.objects.select_related('category', 'restaurant').prefetch_related(
                'variants', 'variants__unit', 'raw_material_links',
                'raw_material_links__raw_material', 'raw_material_links__product_variant',
            ).get(pk=serializer.instance.pk)
            return Response(
                ProductDetailSerializer(product, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = Product.objects.filter(restaurant_id__in=owner_ids).select_related(
        'category', 'restaurant',
    ).prefetch_related('variants', 'variants__unit', 'raw_material_links').annotate(
        raw_material_links_count=Count('raw_material_links', distinct=True),
    ).order_by('name')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(category__name__icontains=search)
        )
    serializer = ProductListSerializer(qs, many=True, context={'request': request})
    return Response({'results': serializer.data})


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def product_detail(request, pk):
    """Get, update, or delete a single product."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        product = Product.objects.select_related('category', 'restaurant').prefetch_related(
            'variants', 'variants__unit', 'raw_material_links', 'raw_material_links__raw_material', 'raw_material_links__product_variant',
        ).get(pk=pk)
    except Product.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if product.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'GET':
        serializer = ProductDetailSerializer(product, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        if isinstance(data.get('variants'), str):
            try:
                data['variants'] = json.loads(data['variants'])
            except Exception:
                data['variants'] = []
        if isinstance(data.get('raw_material_links'), str):
            try:
                data['raw_material_links'] = json.loads(data['raw_material_links'])
            except Exception:
                data['raw_material_links'] = []
        serializer = ProductCreateUpdateSerializer(
            product, data=data, partial=True,
            context={'request': request, 'owner_ids': owner_ids, 'product': product},
        )
        if serializer.is_valid():
            serializer.save()
            product = Product.objects.select_related('category', 'restaurant').prefetch_related(
                'variants', 'variants__unit', 'raw_material_links',
                'raw_material_links__raw_material', 'raw_material_links__product_variant',
            ).get(pk=pk)
            return Response(ProductDetailSerializer(product, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# --- Combos (owner/manager scoped) ---

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def combos_list(request):
    """List combos for owner/manager restaurants. POST to create."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        if request.method == 'POST':
            return Response({'detail': 'You have no restaurants.'}, status=status.HTTP_403_FORBIDDEN)
        return Response({'results': []})
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        if isinstance(data.get('products'), str):
            try:
                data['products'] = json.loads(data['products'])
            except Exception:
                data['products'] = []
        # Normalize products: backend expects a list of ints; FormData/some clients send a dict (e.g. {"0": 1, "1": 2})
        raw_products = data.get('products')
        if isinstance(raw_products, dict):
            try:
                items = sorted(raw_products.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
                data['products'] = [int(v) for _, v in items if v is not None and str(v).strip() != '']
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, list):
            try:
                data['products'] = [int(x) for x in raw_products if x is not None and str(x).strip() != '']
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, (int, float)) and not isinstance(raw_products, bool):
            try:
                data['products'] = [int(raw_products)]
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, str) and raw_products.strip():
            try:
                data['products'] = [int(raw_products.strip())]
            except (ValueError, TypeError):
                data['products'] = []
        else:
            data['products'] = []
        if not data.get('restaurant') and len(owner_ids) == 1:
            data['restaurant'] = owner_ids[0]
        if not data.get('restaurant') and len(owner_ids) > 1:
            return Response(
                {'restaurant': ['Restaurant is required when you have multiple restaurants.']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ComboSetCreateUpdateSerializer(
            data=data,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                ComboSetDetailSerializer(serializer.instance, context={'request': request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    qs = ComboSet.objects.filter(restaurant_id__in=owner_ids).annotate(
        products_count=Count('products', distinct=True),
    ).prefetch_related('products').select_related('restaurant').order_by('name')
    serializer = ComboSetListSerializer(qs, many=True, context={'request': request})
    return Response({'results': serializer.data})


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def combo_detail(request, pk):
    """Get, update, or delete a single combo."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        combo = ComboSet.objects.prefetch_related('products').select_related('restaurant').get(pk=pk)
    except ComboSet.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if combo.restaurant_id not in owner_ids:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        combo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'GET':
        serializer = ComboSetDetailSerializer(combo, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if request.FILES:
            for key in request.FILES:
                data[key] = request.FILES[key]
        if isinstance(data.get('products'), str):
            try:
                data['products'] = json.loads(data['products'])
            except Exception:
                data['products'] = []
        # Normalize products: list of ints (dict from FormData -> list)
        raw_products = data.get('products')
        if isinstance(raw_products, dict):
            try:
                items = sorted(raw_products.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
                data['products'] = [int(v) for _, v in items if v is not None and str(v).strip() != '']
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, list):
            try:
                data['products'] = [int(x) for x in raw_products if x is not None and str(x).strip() != '']
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, (int, float)) and not isinstance(raw_products, bool):
            try:
                data['products'] = [int(raw_products)]
            except (ValueError, TypeError):
                data['products'] = []
        elif isinstance(raw_products, str) and raw_products.strip():
            try:
                data['products'] = [int(raw_products.strip())]
            except (ValueError, TypeError):
                data['products'] = []
        else:
            data['products'] = []
        serializer = ComboSetCreateUpdateSerializer(
            combo, data=data, partial=True,
            context={'request': request, 'owner_ids': owner_ids},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(ComboSetDetailSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_paid_records_list(request):
    """List paid records for owner/manager restaurants; search, date range, pagination. Waiter sees only own records."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    qs = PaidRecord.objects.filter(restaurant_id__in=owner_ids).select_related('restaurant').order_by('-created_at')
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        qs = qs.filter(staff_id=current_staff.id)
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search))
    date_from = request.query_params.get('date_from') or request.query_params.get('start_date')
    date_to = request.query_params.get('date_to') or request.query_params.get('end_date')
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from[:10])
        except (TypeError, ValueError):
            pass
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to[:10])
        except (TypeError, ValueError):
            pass
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = [
        {
            'id': r.id,
            'name': r.name,
            'amount': str(r.amount),
            'payment_method': r.payment_method or '',
            'remarks': r.remarks or '',
            'created_at': r.created_at.isoformat() if r.created_at else '',
        }
        for r in page
    ]
    return paginator.get_paginated_response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_paid_records_stats(request):
    """Total paid amount and count for owner/manager restaurants (optional date range). Waiter sees only own."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_amount': '0', 'count': 0})
    qs = PaidRecord.objects.filter(restaurant_id__in=owner_ids)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        qs = qs.filter(staff_id=current_staff.id)
    date_from = request.query_params.get('date_from') or request.query_params.get('start_date')
    date_to = request.query_params.get('date_to') or request.query_params.get('end_date')
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from[:10])
        except (TypeError, ValueError):
            pass
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to[:10])
        except (TypeError, ValueError):
            pass
    agg = qs.aggregate(total=Sum('amount'), count=Count('id'))
    return Response({
        'total_amount': str(agg['total'] or 0),
        'count': agg['count'] or 0,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_received_records_list(request):
    """List received records for owner/manager restaurants; search, date range, pagination."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    qs = ReceivedRecord.objects.filter(restaurant_id__in=owner_ids).select_related(
        'restaurant', 'customer', 'order'
    ).order_by('-created_at')
    search = (request.query_params.get('search') or '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(remarks__icontains=search))
    date_from = request.query_params.get('date_from') or request.query_params.get('start_date')
    date_to = request.query_params.get('date_to') or request.query_params.get('end_date')
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from[:10])
        except (TypeError, ValueError):
            pass
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to[:10])
        except (TypeError, ValueError):
            pass
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = []
    for r in page:
        results.append({
            'id': r.id,
            'name': r.name,
            'amount': str(r.amount),
            'payment_method': r.payment_method or '',
            'remarks': r.remarks or '',
            'created_at': r.created_at.isoformat() if r.created_at else '',
            'customer_name': r.customer.name if r.customer_id else None,
            'order_id': r.order_id,
        })
    return paginator.get_paginated_response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_received_records_stats(request):
    """Total received amount and count for owner/manager restaurants (optional date range)."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'total_amount': '0', 'count': 0})
    qs = ReceivedRecord.objects.filter(restaurant_id__in=owner_ids)
    date_from = request.query_params.get('date_from') or request.query_params.get('start_date')
    date_to = request.query_params.get('date_to') or request.query_params.get('end_date')
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from[:10])
        except (TypeError, ValueError):
            pass
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to[:10])
        except (TypeError, ValueError):
            pass
    agg = qs.aggregate(total=Sum('amount'), count=Count('id'))
    return Response({
        'total_amount': str(agg['total'] or 0),
        'count': agg['count'] or 0,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_payroll_list(request):
    """Payroll list for owner's staff: staff, restaurant, period, days, per_day, total salary, paid/due, status. Waiter sees only own row."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'count': 0, 'next': None, 'previous': None, 'results': []})
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is None or end_dt is None:
        from datetime import datetime
        today = timezone.now().date()
        start_dt = timezone.make_aware(datetime(today.year, today.month, 1))
        end_dt = timezone.now()
    staff_qs = Staff.objects.filter(restaurant_id__in=owner_ids).select_related('user', 'restaurant').order_by('restaurant__name', 'user__name')
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        staff_qs = staff_qs.filter(id=current_staff.id)
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
def owner_performance(request):
    """Performance stats for current staff (waiter/kitchen): orders_served, average_rating, tips, attendance_days. Optional start_date/end_date."""
    current_staff = _current_staff(request)
    if current_staff is None:
        return Response({'detail': 'Not available.'}, status=status.HTTP_403_FORBIDDEN)
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if not owner_ids:
        return Response({
            'orders_served': 0,
            'average_rating': 0,
            'tips_total': '0',
            'attendance_days': 0,
        })
    start_dt, end_dt = _parse_date_range(request)
    if start_dt is None or end_dt is None:
        from datetime import datetime
        today = timezone.now().date()
        start_dt = timezone.make_aware(datetime(today.year, today.month, 1))
        end_dt = timezone.now()
    start_date, end_date = start_dt.date(), end_dt.date()
    orders_served = Order.objects.filter(
        restaurant_id__in=owner_ids,
        waiter_id=current_staff.id,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).count()
    feedback_qs = Feedback.objects.filter(
        restaurant_id__in=owner_ids,
        order__waiter_id=current_staff.id,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    rating_agg = feedback_qs.aggregate(avg=Avg('rating'))
    average_rating = float(rating_agg['avg'] or 0)
    tips_total = Transaction.objects.filter(
        paid_record__staff_id=current_staff.id,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    attendance_days = Attendance.objects.filter(
        staff_id=current_staff.id,
        date__gte=start_date,
        date__lte=end_date,
        status=AttendanceStatus.PRESENT,
    ).count()
    return Response({
        'orders_served': orders_served,
        'average_rating': round(average_rating, 1),
        'tips_total': str(tips_total),
        'attendance_days': attendance_days,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def owner_report_staff(request):
    """Staff report: filters restaurant, date range, role; table Staff, Restaurant, Role, Attendance days, Salary, Paid, Due, Status."""
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    qs = Customer.objects.filter(id__in=customer_ids).exclude(user__is_restaurant_staff=True)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is None or not owner_ids:
        return Response({'revenue': '0', 'expenses': '0', 'net_profit': '0', 'breakdown': [], 'monthly': []})
    start_dt, end_dt = _parse_date_range(request)
    if not start_dt or not end_dt:
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
    # Build monthly time series for charts
    txn_by_month = Transaction.objects.filter(
        restaurant_id__in=owner_ids,
        transaction_type=TransactionType.IN,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('amount')).order_by('month_key')
    order_by_month = Order.objects.filter(
        restaurant_id__in=owner_ids,
        payment_status__in=['paid', 'success'],
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('total')).order_by('month_key')
    staff_by_month = PaidRecord.objects.filter(
        restaurant_id__in=owner_ids,
        staff__isnull=False,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('amount')).order_by('month_key')
    vendor_by_month = PaidRecord.objects.filter(
        restaurant_id__in=owner_ids,
        vendor__isnull=False,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('amount')).order_by('month_key')
    try:
        from .models import Expenses as ExpensesModel
        other_by_month = ExpensesModel.objects.filter(
            restaurant_id__in=owner_ids,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).annotate(month_key=TruncMonth('created_at')).values('month_key').annotate(amount=Sum('amount')).order_by('month_key')
    except Exception:
        other_by_month = []
    by_month = {}
    for r in txn_by_month:
        key = r['month_key']
        if key not in by_month:
            by_month[key] = {'revenue': Decimal('0'), 'expenses': Decimal('0')}
        by_month[key]['revenue'] += r['amount'] or Decimal('0')
    for r in order_by_month:
        key = r['month_key']
        if key not in by_month:
            by_month[key] = {'revenue': Decimal('0'), 'expenses': Decimal('0')}
        by_month[key]['revenue'] += r['amount'] or Decimal('0')
    for r in staff_by_month:
        key = r['month_key']
        if key not in by_month:
            by_month[key] = {'revenue': Decimal('0'), 'expenses': Decimal('0')}
        by_month[key]['expenses'] += r['amount'] or Decimal('0')
    for r in vendor_by_month:
        key = r['month_key']
        if key not in by_month:
            by_month[key] = {'revenue': Decimal('0'), 'expenses': Decimal('0')}
        by_month[key]['expenses'] += r['amount'] or Decimal('0')
    for r in other_by_month:
        key = r['month_key']
        if key not in by_month:
            by_month[key] = {'revenue': Decimal('0'), 'expenses': Decimal('0')}
        by_month[key]['expenses'] += r['amount'] or Decimal('0')
    monthly = []
    for month_key in sorted(by_month.keys()):
        rev = by_month[month_key]['revenue']
        exp = by_month[month_key]['expenses']
        monthly.append({
            'month': month_key.strftime('%Y-%m') if hasattr(month_key, 'strftime') else str(month_key)[:7],
            'revenue': str(rev),
            'expenses': str(exp),
            'net_profit': str(rev - exp),
        })
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    # Waiter/kitchen see only their own transactions (via paid_record linked to their staff)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        qs = qs.filter(paid_record__staff_id=current_staff.id)
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
    category = (request.query_params.get('category') or '').strip().lower()
    if category and category in [c[0] for c in TransactionCategory.choices]:
        qs = qs.filter(category=category)
    return qs


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuserOrOwner])
def transaction_stats(request):
    qs = Transaction.objects.all()
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is not None:
        qs = qs.filter(restaurant_id__in=owner_ids)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        qs = qs.filter(paid_record__staff_id=current_staff.id)
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
        txn = Transaction.objects.select_related('restaurant', 'restaurant__user', 'paid_record').get(pk=pk)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    owner_ids = _owner_or_manager_restaurant_ids(request)
    if owner_ids is not None and (txn.restaurant_id is None or txn.restaurant_id not in owner_ids):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    # Waiter/kitchen may only view transactions linked to their own staff (paid_record)
    current_staff = _current_staff(request)
    if current_staff is not None and not current_staff.is_manager:
        if not txn.paid_record_id or txn.paid_record.staff_id != current_staff.id:
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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
    owner_ids = _owner_or_manager_restaurant_ids(request)
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


# ---------- Public (no auth): menu by slug & guest order ----------

@api_view(['GET'])
@permission_classes([AllowAny])
def public_menu_by_slug(request, slug):
    """Return restaurant info + categories + active products for public QR menu. No auth."""
    rest = Restaurant.objects.filter(slug=slug).first()
    if not rest:
        return Response({'detail': 'Restaurant not found.'}, status=status.HTTP_404_NOT_FOUND)
    from .serializers import _build_media_url
    logo_url = None
    if rest.logo:
        logo_url = _build_media_url(request, rest.logo.url if hasattr(rest.logo, 'url') else str(rest.logo))
    categories_qs = Category.objects.filter(restaurant=rest).order_by('name')
    categories_data = []
    for c in categories_qs:
        cat_image_url = None
        if c.image:
            cat_image_url = _build_media_url(request, c.image.url if hasattr(c.image, 'url') else str(c.image))
        categories_data.append({
            'id': c.id,
            'name': c.name,
            'image_url': cat_image_url,
        })
    products_qs = Product.objects.filter(
        restaurant=rest,
        is_active=True,
    ).select_related('category').prefetch_related('variants', 'variants__unit').order_by('category__name', 'name')
    products_data = []
    for p in products_qs:
        img_url = None
        if p.image:
            img_url = _build_media_url(request, p.image.url if hasattr(p.image, 'url') else str(p.image))
        variants_data = []
        for v in p.variants.all():
            variants_data.append({
                'id': v.id,
                'unit_name': v.unit.name if v.unit_id else '',
                'unit_symbol': v.unit.symbol or '',
                'price': str(v.get_final_price()),
            })
        products_data.append({
            'id': p.id,
            'name': p.name,
            'category_id': p.category_id,
            'category_name': p.category.name if p.category_id else '',
            'image_url': img_url,
            'dish_type': getattr(p, 'dish_type', 'veg'),
            'variants': variants_data,
        })
    return Response({
        'restaurant': {
            'id': rest.id,
            'name': rest.name,
            'slug': rest.slug,
            'logo_url': logo_url,
            'address': rest.address or '',
            'phone': rest.phone or '',
            'is_open': rest.is_open,
        },
        'categories': categories_data,
        'products': products_data,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def public_order_create(request, slug):
    """Create order for restaurant by slug (guest). Body: phone, name?, country_code?, items: [{ product_id or product_variant_id, quantity }]."""
    rest = Restaurant.objects.filter(slug=slug).first()
    if not rest:
        return Response({'detail': 'Restaurant not found.'}, status=status.HTTP_404_NOT_FOUND)
    if not rest.is_open:
        return Response({'detail': 'Restaurant is currently closed.'}, status=status.HTTP_400_BAD_REQUEST)
    data = request.data if hasattr(request.data, 'get') else {}
    phone = (data.get('phone') or '').strip()
    if not phone:
        return Response({'detail': 'Phone is required.'}, status=status.HTTP_400_BAD_REQUEST)
    name = (data.get('name') or '').strip() or None
    country_code = (data.get('country_code') or '').strip() or None
    items_data = data.get('items') or []
    if not items_data:
        return Response({'detail': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)
    from .services import get_or_create_customer_for_restaurant
    customer, _ = get_or_create_customer_for_restaurant(rest, phone, name=name, country_code=country_code)
    if not customer:
        return Response({'detail': 'Invalid customer.'}, status=status.HTTP_400_BAD_REQUEST)
    order_total = Decimal('0')
    line_items = []
    for row in items_data:
        qty = Decimal(str(row.get('quantity') or 1))
        if qty <= 0:
            continue
        pv_id = row.get('product_variant_id')
        prod_id = row.get('product_id')
        unit_price = None
        product_variant_id = None
        product_id = None
        if pv_id:
            try:
                pv = ProductVariant.objects.select_related('product').get(
                    pk=pv_id, product__restaurant_id=rest.id
                )
                unit_price = pv.get_final_price()
                product_variant_id = pv.id
                product_id = pv.product_id
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                pass
        if unit_price is None and prod_id:
            try:
                prod = Product.objects.filter(pk=prod_id, restaurant_id=rest.id, is_active=True).first()
                if prod:
                    first_v = prod.variants.first()
                    if first_v:
                        unit_price = first_v.get_final_price()
                        product_variant_id = first_v.id
                        product_id = prod.id
            except Exception:
                pass
        if unit_price is not None and (product_variant_id or product_id):
            line_total = unit_price * qty
            order_total += line_total
            line_items.append({
                'product_id': product_id,
                'product_variant_id': product_variant_id,
                'price': unit_price,
                'quantity': qty,
                'total': line_total,
            })
    if not line_items:
        return Response({'detail': 'No valid items.'}, status=status.HTTP_400_BAD_REQUEST)
    service_charge = getattr(rest, 'default_service_charge', None) or Decimal('0')
    order_total_with_charge = order_total + service_charge
    order = Order.objects.create(
        restaurant_id=rest.id,
        customer_id=customer.id,
        table_id=None,
        table_number=None,
        order_type=OrderType.PACKING,
        address=None,
        status='pending',
        payment_status='pending',
        payment_method=data.get('payment_method') or '',
        waiter_id=None,
        total=order_total_with_charge,
        service_charge=service_charge,
    )
    for line in line_items:
        OrderItem.objects.create(
            order=order,
            product_id=line.get('product_id'),
            product_variant_id=line.get('product_variant_id'),
            combo_set_id=None,
            price=line['price'],
            quantity=line['quantity'],
            total=line['total'],
        )
    order.refresh_from_db()
    return Response({
        'order_id': order.id,
        'total': str(order.total),
        'message': 'Order placed successfully.',
    }, status=status.HTTP_201_CREATED)


# ---------- Customers (super admin, for receiver picker) ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def customer_list(request):
    qs = Customer.objects.exclude(user__is_restaurant_staff=True).order_by('-created_at')
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


# ---------- Customer-scoped API (logged-in customer only) ----------

def _current_customer(request):
    """Return Customer instance for request.user if they have a linked Customer profile; else None."""
    if not request.user or not request.user.is_authenticated:
        return None
    return getattr(request.user, 'customer_profile', None)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_dashboard_stats(request):
    """Dashboard stats for current customer: orders count, recent orders, restaurants linked, credit summary."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    total_orders = Order.objects.filter(customer=cust).count()
    recent_orders_count = Order.objects.filter(customer=cust).order_by('-created_at')[:10].count()
    restaurants_linked = CustomerRestaurant.objects.filter(customer=cust).count()
    credit_agg = CustomerRestaurant.objects.filter(customer=cust).aggregate(
        to_pay=Coalesce(Sum('to_pay'), Decimal('0')),
        to_receive=Coalesce(Sum('to_receive'), Decimal('0')),
    )
    feedback_count = Feedback.objects.filter(customer=cust).count()
    # Orders by day (last 7 days) for line chart
    today = timezone.now().date()
    orders_by_day = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        cnt = Order.objects.filter(customer=cust, created_at__date=d).count()
        orders_by_day.append({'date': d.isoformat(), 'count': cnt})
    return Response({
        'total_orders': total_orders,
        'recent_orders_count': recent_orders_count,
        'restaurants_linked': restaurants_linked,
        'total_to_pay': str(credit_agg['to_pay']),
        'total_to_receive': str(credit_agg['to_receive']),
        'feedback_count': feedback_count,
        'orders_by_day': orders_by_day,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_restaurants_list(request):
    """List restaurants for customer browse (read-only). Paginated."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    qs = Restaurant.objects.all().order_by('name')
    ordering = (request.query_params.get('ordering') or 'name').strip()
    if ordering.lstrip('-') in ('name', 'created_at', 'slug'):
        qs = qs.order_by(ordering)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = []
    for rest in page:
        logo_url = None
        if rest.logo:
            logo_url = _build_media_url(request, rest.logo.url if hasattr(rest.logo, 'url') else str(rest.logo))
        results.append({
            'id': rest.id,
            'name': rest.name,
            'slug': rest.slug,
            'address': rest.address or '',
            'logo_url': logo_url,
            'is_open': rest.is_open,
        })
    return paginator.get_paginated_response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_restaurant_detail(request, pk):
    """Restaurant detail + categories + products for customer (read-only menu)."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        rest = Restaurant.objects.get(pk=pk)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    logo_url = None
    if rest.logo:
        logo_url = _build_media_url(request, rest.logo.url if hasattr(rest.logo, 'url') else str(rest.logo))
    categories_qs = Category.objects.filter(restaurant=rest).order_by('name')
    categories_data = []
    for c in categories_qs:
        cat_image_url = None
        if c.image:
            cat_image_url = _build_media_url(request, c.image.url if hasattr(c.image, 'url') else str(c.image))
        categories_data.append({'id': c.id, 'name': c.name, 'image_url': cat_image_url})
    products_qs = Product.objects.filter(
        restaurant=rest, is_active=True,
    ).select_related('category').prefetch_related('variants', 'variants__unit').order_by('category__name', 'name')
    products_data = []
    for p in products_qs:
        img_url = None
        if p.image:
            img_url = _build_media_url(request, p.image.url if hasattr(p.image, 'url') else str(p.image))
        variants_data = [
            {'id': v.id, 'unit_name': v.unit.name if v.unit_id else '', 'unit_symbol': v.unit.symbol or '', 'price': str(v.get_final_price())}
            for v in p.variants.all()
        ]
        products_data.append({
            'id': p.id, 'name': p.name, 'category_id': p.category_id, 'category_name': p.category.name if p.category_id else '',
            'image_url': img_url, 'dish_type': getattr(p, 'dish_type', 'veg'), 'variants': variants_data,
        })
    default_service_charge = getattr(rest, 'default_service_charge', None)
    return Response({
        'restaurant': {
            'id': rest.id, 'name': rest.name, 'slug': rest.slug, 'logo_url': logo_url,
            'address': rest.address or '', 'phone': rest.phone or '', 'is_open': rest.is_open,
            'default_service_charge': str(default_service_charge) if default_service_charge is not None else '0',
        },
        'categories': categories_data,
        'products': products_data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_restaurant_tables(request, pk):
    """List tables for a restaurant (read-only). Used by customer to choose table for Table/Packing order type."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        rest = Restaurant.objects.get(pk=pk)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    tables = Table.objects.filter(restaurant=rest).order_by('floor', 'name')
    results = [{'id': t.id, 'name': t.name} for t in tables]
    return Response({'results': results})


def _customer_order_create(request):
    """Create order for logged-in customer. Body: restaurant_id, items, order_type, payment_method (cash|e_wallet only), table_id?, table_number?, address?. Service charge fixed at 10 NPR."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    data = request.data if hasattr(request.data, 'get') else {}
    restaurant_id = data.get('restaurant_id')
    if not restaurant_id:
        return Response({'detail': 'restaurant_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        restaurant_id = int(restaurant_id)
    except (TypeError, ValueError):
        return Response({'detail': 'Valid restaurant_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        rest = Restaurant.objects.get(pk=restaurant_id)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Restaurant not found.'}, status=status.HTTP_404_NOT_FOUND)
    if not rest.is_open:
        return Response({'detail': 'Restaurant is currently closed.'}, status=status.HTTP_400_BAD_REQUEST)
    order_type_raw = (data.get('order_type') or 'table').strip().lower()
    if order_type_raw not in (OrderType.TABLE, OrderType.PACKING, OrderType.DELIVERY):
        order_type_raw = OrderType.TABLE
    # Customer orders: only Cash or Online (e_wallet) allowed
    payment_method = (data.get('payment_method') or '').strip() or None
    if payment_method not in ('cash', 'e_wallet'):
        payment_method = 'cash'
    table_id = data.get('table_id')
    table_number = (data.get('table_number') or '').strip() or None
    address = (data.get('address') or '').strip() or None
    # Optional table_id: must belong to this restaurant
    if table_id is not None:
        try:
            tbl = Table.objects.filter(pk=table_id, restaurant_id=rest.id).first()
            if tbl:
                table_id = tbl.id
                if not table_number:
                    table_number = tbl.name
            else:
                table_id = None
        except (TypeError, ValueError):
            table_id = None
    else:
        table_id = None
    items_data = data.get('items') or []
    if not items_data:
        return Response({'detail': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)
    order_total = Decimal('0')
    line_items = []
    for row in items_data:
        qty = Decimal(str(row.get('quantity') or 1))
        if qty <= 0:
            continue
        pv_id = row.get('product_variant_id')
        prod_id = row.get('product_id')
        unit_price = None
        product_variant_id = None
        product_id = None
        if pv_id:
            try:
                pv = ProductVariant.objects.select_related('product').get(
                    pk=pv_id, product__restaurant_id=rest.id
                )
                unit_price = pv.get_final_price()
                product_variant_id = pv.id
                product_id = pv.product_id
            except (ProductVariant.DoesNotExist, TypeError, ValueError):
                pass
        if unit_price is None and prod_id:
            try:
                prod = Product.objects.filter(pk=prod_id, restaurant_id=rest.id, is_active=True).first()
                if prod:
                    first_v = prod.variants.first()
                    if first_v:
                        unit_price = first_v.get_final_price()
                        product_variant_id = first_v.id
                        product_id = prod.id
            except Exception:
                pass
        if unit_price is not None and (product_variant_id or product_id):
            line_total = unit_price * qty
            order_total += line_total
            line_items.append({
                'product_id': product_id,
                'product_variant_id': product_variant_id,
                'price': unit_price,
                'quantity': qty,
                'total': line_total,
            })
    if not line_items:
        return Response({'detail': 'No valid items.'}, status=status.HTTP_400_BAD_REQUEST)
    # Fixed 10 NPR service charge for customer-created orders (do not accept from client)
    service_charge = Decimal('10')
    order_total_with_charge = order_total + service_charge
    order = Order.objects.create(
        restaurant=rest,
        customer=cust,
        table_id=table_id,
        table_number=table_number,
        order_type=order_type_raw,
        address=address,
        status='pending',
        payment_status='pending',
        payment_method=payment_method or '',
        waiter_id=None,
        total=order_total_with_charge,
        service_charge=service_charge,
    )
    for line in line_items:
        OrderItem.objects.create(
            order=order,
            product_id=line.get('product_id'),
            product_variant_id=line.get('product_variant_id'),
            combo_set_id=None,
            price=line['price'],
            quantity=line['quantity'],
            total=line['total'],
        )
    order.refresh_from_db()
    return Response({
        'order_id': order.id,
        'total': str(order.total),
        'service_charge': str(order.service_charge) if order.service_charge is not None else '0',
        'message': 'Order placed successfully.',
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def customer_orders_list(request):
    """GET: List orders for current customer. POST: Create order for current customer."""
    if request.method == 'POST':
        return _customer_order_create(request)
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    qs = Order.objects.filter(customer=cust).annotate(items_count=Count('items')).select_related(
        'restaurant', 'table', 'waiter', 'waiter__user'
    ).order_by('-created_at')
    status_param = request.query_params.get('status', '').strip()
    if status_param:
        qs = qs.filter(status=status_param)
    payment_status_param = request.query_params.get('payment_status', '').strip()
    if payment_status_param:
        qs = qs.filter(payment_status=payment_status_param)
    restaurant_id = request.query_params.get('restaurant', '').strip()
    if restaurant_id:
        try:
            qs = qs.filter(restaurant_id=int(restaurant_id))
        except (TypeError, ValueError):
            pass
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    # Stats for this customer
    stats_qs = Order.objects.filter(customer=cust)
    total_orders = stats_qs.count()
    pending_count = stats_qs.filter(status='pending').count()
    paid_count = stats_qs.filter(payment_status='paid').count()
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = []
    for o in page:
        results.append({
            'id': o.id,
            'restaurant_id': o.restaurant_id,
            'restaurant_name': o.restaurant.name if o.restaurant_id else '',
            'table_number': o.table_number or (o.table.name if o.table_id else ''),
            'order_type': o.order_type,
            'total': str(o.total),
            'status': o.status,
            'payment_status': o.payment_status,
            'items_count': getattr(o, 'items_count', 0),
            'created_at': o.created_at.isoformat() if hasattr(o.created_at, 'isoformat') else str(o.created_at),
        })
    resp = paginator.get_paginated_response(results)
    resp.data['stats'] = {'total_orders': total_orders, 'pending_count': pending_count, 'paid_count': paid_count}
    return resp


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_order_detail(request, pk):
    """Order detail for current customer (own order only)."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        order = Order.objects.filter(customer=cust).select_related(
            'restaurant', 'table', 'waiter', 'waiter__user'
        ).prefetch_related(
            'items__product', 'items__product_variant', 'items__product_variant__product', 'items__combo_set'
        ).get(pk=pk)
    except Order.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    items = []
    subtotal = Decimal('0')
    for item in order.items.all():
        line_total = item.total
        subtotal += line_total
        items.append({
            'id': item.id,
            'name': _order_item_name(item),
            'quantity': str(item.quantity),
            'price': str(item.price),
            'total': str(line_total),
        })
    has_feedback = Feedback.objects.filter(order=order, customer=cust).exists()
    return Response({
        'id': order.id,
        'restaurant_id': order.restaurant_id,
        'restaurant_name': order.restaurant.name if order.restaurant_id else '',
        'table_number': order.table_number or (order.table.name if order.table_id else ''),
        'order_type': order.order_type,
        'status': order.status,
        'payment_status': order.payment_status,
        'payment_method': order.payment_method or '',
        'subtotal': str(subtotal),
        'service_charge': str(order.service_charge) if order.service_charge is not None else None,
        'discount': str(order.discount) if order.discount is not None else None,
        'total': str(order.total),
        'created_at': order.created_at.isoformat() if hasattr(order.created_at, 'isoformat') else str(order.created_at),
        'items': items,
        'has_feedback': has_feedback,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_transactions_list(request):
    """List received records (payments) for current customer. Read-only."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    qs = ReceivedRecord.objects.filter(customer=cust).select_related(
        'restaurant', 'order'
    ).order_by('-created_at')
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    total_amount = qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    results = []
    for r in page:
        results.append({
            'id': r.id,
            'date': r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
            'type': 'payment',
            'amount': str(r.amount),
            'payment_method': r.payment_method or '',
            'reference': str(r.order_id) if r.order_id else str(r.id),
            'restaurant_id': r.restaurant_id,
            'restaurant_name': r.restaurant.name if r.restaurant_id else '',
            'order_id': r.order_id,
        })
    return Response({
        'stats': {'total_amount': str(total_amount), 'count': qs.count()},
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': results,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_transaction_detail(request, pk):
    """Single received record for current customer."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        r = ReceivedRecord.objects.filter(customer=cust).select_related('restaurant', 'order').get(pk=pk)
    except ReceivedRecord.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        'id': r.id,
        'date': r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
        'type': 'payment',
        'amount': str(r.amount),
        'payment_method': r.payment_method or '',
        'reference': str(r.order_id) if r.order_id else str(r.id),
        'restaurant_id': r.restaurant_id,
        'restaurant_name': r.restaurant.name if r.restaurant_id else '',
        'order_id': r.order_id,
        'remarks': r.remarks or '',
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_transactions_analytics(request):
    """Order-based transaction analytics for current customer: table rows, by_restaurant, top_products, monthly trend."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    qs = Order.objects.filter(customer=cust).select_related('restaurant').prefetch_related(
        'items__product', 'items__product_variant', 'items__product_variant__product', 'items__combo_set'
    ).order_by('-created_at')
    start_date = request.query_params.get('start_date', '').strip()[:10]
    if start_date:
        try:
            qs = qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    end_date = request.query_params.get('end_date', '').strip()[:10]
    if end_date:
        try:
            qs = qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    orders = list(qs)
    table_rows = []
    by_restaurant_map = {}
    product_totals = {}
    for order in orders:
        product_names = []
        for item in order.items.all():
            name = _order_item_name(item)
            product_names.append(name)
            product_totals[name] = product_totals.get(name, {'total': Decimal('0'), 'count': 0})
            product_totals[name]['total'] += item.total
            product_totals[name]['count'] += 1
        table_rows.append({
            'date': order.created_at.isoformat() if hasattr(order.created_at, 'isoformat') else str(order.created_at),
            'restaurant_name': order.restaurant.name if order.restaurant_id else '',
            'order_id': order.id,
            'products': product_names,
            'amount_paid': str(order.total),
            'payment_method': order.payment_method or '',
        })
        rname = order.restaurant.name if order.restaurant_id else ''
        if rname not in by_restaurant_map:
            by_restaurant_map[rname] = {'total_paid': Decimal('0'), 'order_count': 0}
        by_restaurant_map[rname]['total_paid'] += order.total
        by_restaurant_map[rname]['order_count'] += 1
    by_restaurant = [
        {'restaurant_name': k, 'total_paid': str(v['total_paid']), 'order_count': v['order_count']}
        for k, v in by_restaurant_map.items()
    ]
    top_products = sorted(
        [{'product_name': k, 'total_spent': str(v['total']), 'count': v['count']} for k, v in product_totals.items()],
        key=lambda x: Decimal(x['total_spent']),
        reverse=True,
    )[:10]
    monthly_qs = Order.objects.filter(customer=cust)
    if start_date:
        try:
            monthly_qs = monthly_qs.filter(created_at__date__gte=start_date)
        except (TypeError, ValueError):
            pass
    if end_date:
        try:
            monthly_qs = monthly_qs.filter(created_at__date__lte=end_date)
        except (TypeError, ValueError):
            pass
    monthly_agg = list(
        monthly_qs.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Coalesce(Sum('total'), Decimal('0')))
        .order_by('month')
    )
    monthly = [
        {'month': (m['month'].strftime('%Y-%m') if m['month'] else ''), 'total': str(m['total'])}
        for m in monthly_agg
    ]
    return Response({
        'table_rows': table_rows,
        'by_restaurant': by_restaurant,
        'top_products': top_products,
        'monthly': monthly,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_credits_list(request):
    """Credits/balance per restaurant for current customer. Read-only."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    qs = CustomerRestaurant.objects.filter(customer=cust).select_related('restaurant').order_by('restaurant__name')
    agg = qs.aggregate(
        total_to_pay=Coalesce(Sum('to_pay'), Decimal('0')),
        total_to_receive=Coalesce(Sum('to_receive'), Decimal('0')),
    )
    results = []
    for cr in qs:
        results.append({
            'id': cr.id,
            'restaurant_id': cr.restaurant_id,
            'restaurant_name': cr.restaurant.name if cr.restaurant_id else '',
            'to_pay': str(cr.to_pay),
            'to_receive': str(cr.to_receive),
            'updated_at': cr.updated_at.isoformat() if hasattr(cr.updated_at, 'isoformat') else str(cr.updated_at),
        })
    return Response({
        'stats': {
            'total_to_pay': str(agg['total_to_pay']),
            'total_to_receive': str(agg['total_to_receive']),
            'restaurants_linked': qs.count(),
        },
        'results': results,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def customer_feedback_list(request):
    """GET: List feedback for current customer. POST: Create feedback for an order."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'POST':
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        order_id = data.get('order_id') or data.get('order')
        if not order_id:
            return Response({'detail': 'order_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid order_id.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = Order.objects.filter(customer=cust).get(pk=order_id)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found or not yours.'}, status=status.HTTP_404_NOT_FOUND)
        if Feedback.objects.filter(order=order, customer=cust).exists():
            return Response({'detail': 'Feedback already submitted for this order.'}, status=status.HTTP_400_BAD_REQUEST)
        rating = data.get('rating')
        if rating is None:
            return Response({'detail': 'rating is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid rating.'}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= rating <= 5:
            return Response({'detail': 'Rating must be between 1 and 5.'}, status=status.HTTP_400_BAD_REQUEST)
        review = (data.get('review') or '').strip()
        Feedback.objects.create(
            restaurant=order.restaurant,
            customer=cust,
            order=order,
            rating=rating,
            review=review,
        )
        return Response({'detail': 'Feedback submitted.'}, status=status.HTTP_201_CREATED)
    qs = Feedback.objects.filter(customer=cust).select_related('restaurant', 'order').order_by('-created_at')
    from django.db.models import Avg
    avg_rating = qs.aggregate(a=Avg('rating'))['a']
    total = qs.count()
    by_rating = dict(Feedback.objects.filter(customer=cust).values('rating').annotate(c=Count('id')).values_list('rating', 'c'))
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = FeedbackListSerializer(page, many=True, context={'request': request})
    data = serializer.data
    for i, row in enumerate(data):
        if i < len(page):
            row['restaurant_id'] = page[i].restaurant_id
            row['restaurant_name'] = page[i].restaurant.name if page[i].restaurant_id else ''
    return Response({
        'stats': {
            'average_rating': float(avg_rating) if avg_rating is not None else None,
            'total': total,
            'by_rating': by_rating,
        },
        'count': paginator.page.paginator.count,
        'next': paginator.get_next_link(),
        'previous': paginator.get_previous_link(),
        'results': data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_feedback_detail(request, pk):
    """Single feedback for current customer."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    try:
        fb = Feedback.objects.filter(customer=cust).select_related('restaurant', 'order').get(pk=pk)
    except Feedback.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = FeedbackDetailSerializer(fb, context={'request': request})
    data = serializer.data
    data['restaurant_id'] = fb.restaurant_id
    data['restaurant_name'] = fb.restaurant.name if fb.restaurant_id else ''
    data['order_id'] = fb.order_id
    return Response(data)


def _customer_me_response(cust, request):
    """Build GET/PATCH response for customer profile, including image_url from linked User when present."""
    payload = {
        'id': cust.id,
        'name': cust.name,
        'phone': cust.phone,
        'country_code': cust.country_code,
        'address': cust.address or '',
    }
    if cust.user_id:
        user = cust.user
        if user.image:
            url = getattr(user.image, 'url', None) or str(user.image)
            payload['image_url'] = _build_media_url(request, url)
        else:
            payload['image_url'] = None
    return payload


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def customer_me(request):
    """GET: Customer profile. PATCH: Update name, phone, country_code, address, image. Sync to User when present."""
    cust = _current_customer(request)
    if not cust:
        return Response({'detail': 'Customer profile not found.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        return Response(_customer_me_response(cust, request))
    # PATCH: accept JSON or multipart (for image upload)
    data = request.data if hasattr(request.data, 'get') else {}
    if 'name' in data and data.get('name') is not None:
        cust.name = data['name']
    if 'phone' in data and data.get('phone') is not None:
        cust.phone = str(data['phone']).strip()
    if 'country_code' in data and data.get('country_code') is not None:
        cust.country_code = str(data['country_code']).strip()
    if 'address' in data:
        cust.address = (data.get('address') or '').strip()
    cust.save()
    image_file = request.FILES.get('image') if hasattr(request, 'FILES') else None
    if cust.user_id:
        user = cust.user
        if image_file:
            user.image = image_file
        if 'name' in data and data.get('name') is not None:
            user.name = data['name']
        if 'phone' in data and data.get('phone') is not None:
            user.phone = str(data['phone']).strip()
        if 'country_code' in data and data.get('country_code') is not None:
            user.country_code = str(data['country_code']).strip()
        user.save()
    return Response(_customer_me_response(cust, request))
