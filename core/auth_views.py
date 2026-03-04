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
