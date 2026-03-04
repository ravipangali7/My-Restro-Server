from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta
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
)
from .models import PaymentStatus
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
    ShareholderWithdrawalListSerializer,
    ShareholderWithdrawalCreateSerializer,
    ShareholderWithdrawalDetailSerializer,
    TransactionSerializer,
    TransactionDetailSerializer,
    QrStandOrderListSerializer,
    QrStandOrderDetailSerializer,
    QrStandOrderCreateSerializer,
    QrStandOrderUpdateSerializer,
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
    if request.query_params.get('has_due') == 'true':
        qs = qs.filter(due_balance__gt=0)
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


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def due_stats(request):
    """Stats for Due listing: total due count/amount, over threshold, outstanding."""
    qs_with_due = Restaurant.objects.filter(due_balance__gt=0)
    total_due_count = qs_with_due.count()
    total_due_amount = qs_with_due.aggregate(s=Sum('due_balance'))['s'] or 0
    try:
        ss = SuperSetting.objects.first()
        threshold = (ss.due_threshold or 0) if ss else 0
    except Exception:
        threshold = 0
    over_threshold_qs = Restaurant.objects.filter(due_balance__gt=threshold) if threshold else qs_with_due
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
@permission_classes([IsAuthenticated, IsSuperuser])
def transaction_stats(request):
    qs = Transaction.objects.all()
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
@permission_classes([IsAuthenticated, IsSuperuser])
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
@permission_classes([IsAuthenticated, IsSuperuser])
def transaction_detail(request, pk):
    try:
        txn = Transaction.objects.select_related('restaurant', 'restaurant__user').get(pk=pk)
    except Transaction.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    serializer = TransactionDetailSerializer(txn, context={'request': request})
    return Response(serializer.data)


# ---------- QR Stand Order ----------

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def qr_stand_order_price(request):
    """Return per_qr_stand_price from SuperSetting for real-time total calculation in add form."""
    from .services import get_super_setting
    ss = get_super_setting()
    price = ss.per_qr_stand_price or 0
    return Response({'per_qr_stand_price': str(price)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSuperuser])
def qr_stand_order_stats(request):
    qs = QrStandOrder.objects.all()
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
@permission_classes([IsAuthenticated, IsSuperuser])
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
    status_filter = request.query_params.get('status', '').strip().lower()
    if status_filter in ('pending', 'accepted', 'shipped', 'delivered'):
        qs = qs.filter(status=status_filter)
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = QrStandOrderListSerializer(page, many=True, context={'request': request})
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET', 'PATCH', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsSuperuser])
def qr_stand_order_detail(request, pk):
    try:
        order = QrStandOrder.objects.select_related('restaurant').get(pk=pk)
    except QrStandOrder.DoesNotExist:
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
@permission_classes([IsAuthenticated, IsSuperuser])
def qr_stand_order_pay(request, pk):
    from .services import pay_qr_stand_order
    try:
        order = QrStandOrder.objects.select_related('restaurant').get(pk=pk)
    except QrStandOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        pay_qr_stand_order(order)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    order.refresh_from_db()
    serializer = QrStandOrderDetailSerializer(order, context={'request': request})
    return Response(serializer.data)
