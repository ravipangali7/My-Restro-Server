from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import User, Restaurant, SuperSetting, ShareholderWithdrawal
from .permissions import IsSuperuser
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
)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


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


# ---------- Restaurants ----------

def _restaurant_queryset(request):
    qs = Restaurant.objects.all().select_related('user').order_by('-created_at')
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
@permission_classes([IsAuthenticated, IsSuperuser])
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
@permission_classes([IsAuthenticated, IsSuperuser])
def restaurant_detail(request, pk):
    try:
        rest = Restaurant.objects.select_related('user').get(pk=pk)
    except Restaurant.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        serializer = RestaurantDetailSerializer(rest, context={'request': request})
        return Response(serializer.data)
    if request.method in ('PATCH', 'PUT'):
        serializer = RestaurantCreateUpdateSerializer(rest, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(RestaurantDetailSerializer(serializer.instance, context={'request': request}).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    rest.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def restaurant_stats(request):
    qs = Restaurant.objects.all()
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
        serializer = OwnerCreateUpdateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            user = serializer.instance
            user.is_shareholder = True
            user.save(update_fields=['is_shareholder'])
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
    # Pie chart: share distribution (percentages per shareholder)
    dist = []
    for u in shareholders:
        dist.append({'name': u.name or str(u.phone), 'value': float(u.share_percentage or 0)})
    return Response({
        'total_shareholders': total_sh,
        'system_balance': str(system_balance),
        'shareholder_balance': str(sh_balance),
        'pending_withdrawal_balance': str(pending_w),
        'share_distribution': dist,
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
