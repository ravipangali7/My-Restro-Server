from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Safe user fields for API responses; no password."""

    class Meta:
        model = User
        fields = [
            'id',
            'name',
            'phone',
            'country_code',
            'is_superuser',
            'is_owner',
            'is_restaurant_staff',
            'kyc_status',
            'is_shareholder',
            'share_percentage',
            'balance',
            'due_balance',
            'created_at',
        ]
        read_only_fields = fields
