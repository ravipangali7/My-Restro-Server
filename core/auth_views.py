from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import User
from .serializers import UserSerializer


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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    """Return current user payload. Requires Token auth."""
    return Response({'user': UserSerializer(request.user).data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """Invalidate current user's token."""
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def _role_from_user(user):
    """Derive role from user flags (mirrors frontend deriveRole)."""
    if getattr(user, 'is_superuser', False):
        return 'super_admin'
    if getattr(user, 'is_owner', False):
        return 'owner'
    if getattr(user, 'is_restaurant_staff', False):
        staff_role = getattr(user, 'staff_role', None)
        if staff_role == 'manager':
            return 'manager'
        if staff_role == 'waiter':
            return 'waiter'
        if staff_role == 'kitchen':
            return 'kitchen'
    return 'customer'


# Menu items for sidebar. Each: path, label, icon (Lucide icon key for frontend).
SUPER_ADMIN_MENU = [
    {'path': '/owners', 'label': 'Owners', 'icon': 'Users'},
    {'path': '/restaurants', 'label': 'Restaurant', 'icon': 'Building2'},
    {'path': '/kyc', 'label': 'KYC verifications', 'icon': 'Shield'},
    {'path': '/shareholders', 'label': 'Shareholder', 'icon': 'PieChart'},
]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def menu(request):
    """Return sidebar menu for the authenticated user based on role."""
    role = _role_from_user(request.user)
    if role == 'super_admin':
        return Response(SUPER_ADMIN_MENU)
    # Other roles: return empty list; frontend uses static sidebarConfigs for now.
    return Response([])
