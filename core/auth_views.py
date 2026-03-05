from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import User, Customer
from .serializers import UserSerializer

MIN_PASSWORD_LENGTH = 6


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    POST body: { "country_code": "+91", "phone": "9876543210", "password": "..." }
    Returns: { "token": "<key>", "user": {...} } or 400 with detail message.
    """
    country_code = (request.data.get('country_code') or '').strip()
    phone = (request.data.get('phone') or '').strip()
    password = request.data.get('password')

    if not phone:
        return Response(
            {'detail': 'User with this phone number doesn\'t exist.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(country_code=country_code, phone=phone).first()

    if not user:
        if User.objects.filter(phone=phone).exists():
            return Response(
                {'detail': 'Wrong country code.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': 'User with this phone number doesn\'t exist.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not user.check_password(password):
        return Response(
            {'detail': 'Password is wrong.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    POST body: { "name": "...", "country_code": "+91", "phone": "...", "password": "..." }
    Creates a customer-only User (no owner/staff/shareholder). Optionally links a Customer row.
    Returns: { "token": "<key>", "user": {...} } for auto-login, or 400 with detail.
    """
    name = (request.data.get('name') or '').strip()
    country_code = (request.data.get('country_code') or '').strip()
    phone = (request.data.get('phone') or '').strip()
    password = request.data.get('password')

    if not name:
        return Response(
            {'detail': 'Name is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not country_code:
        return Response(
            {'detail': 'Country code is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not phone:
        return Response(
            {'detail': 'Phone number is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not password:
        return Response(
            {'detail': 'Password is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        return Response(
            {'detail': f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if User.objects.filter(country_code=country_code, phone=phone).exists():
        return Response(
            {'detail': 'A user with this phone number already exists.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    username = (country_code or '') + (phone or '')
    user = User(
        username=username,
        name=name,
        country_code=country_code,
        phone=phone,
        is_owner=False,
        is_restaurant_staff=False,
        is_shareholder=False,
    )
    user.set_password(password)
    user.save()

    customer = Customer.objects.filter(country_code=country_code, phone=phone).first()
    if customer:
        customer.user = user
        customer.name = name
        customer.save(update_fields=['user', 'name'])
    else:
        Customer.objects.create(
            user=user,
            name=name,
            phone=phone,
            country_code=country_code,
        )

    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        'token': token.key,
        'user': UserSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    """GET: return current user (with image_url, last_login). PATCH: update name, image, and/or password."""
    user = request.user
    if request.method == 'GET':
        return Response({'user': UserSerializer(user, context={'request': request}).data})
    # PATCH
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.data
    else:
        data = request.data
    updated = False
    if 'name' in data and data['name'] is not None:
        user.name = data['name']
        updated = True
    if 'image' in data:
        user.image = data['image']
        updated = True
    # Optional: update phone and country_code (validate uniqueness)
    new_phone = data.get('phone')
    new_country_code = data.get('country_code')
    if new_phone is not None or new_country_code is not None:
        cc = (new_country_code or getattr(user, 'country_code', '') or '').strip()
        ph = (new_phone or getattr(user, 'phone', '') or '').strip()
        if not ph:
            return Response(
                {'detail': 'Phone number is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(country_code=cc, phone=ph).exclude(pk=user.pk).exists():
            return Response(
                {'detail': 'A user with this phone number already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.country_code = cc
        user.phone = ph
        updated = True
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    if current_password is not None and new_password is not None:
        if not user.check_password(current_password):
            return Response(
                {'detail': 'Current password is wrong.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(new_password)
        updated = True
    if updated:
        user.save()
    return Response({'user': UserSerializer(user, context={'request': request}).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """Invalidate current user's token."""
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
