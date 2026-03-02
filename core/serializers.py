from rest_framework import serializers
from .models import User, Staff


class UserSerializer(serializers.ModelSerializer):
    """Safe user fields for API responses; no password."""
    staff_role = serializers.SerializerMethodField()

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
            'staff_role',
            'kyc_status',
            'is_shareholder',
            'share_percentage',
            'balance',
            'due_balance',
            'created_at',
        ]
        read_only_fields = fields

    def get_staff_role(self, obj):
        staff = obj.staff_profiles.first()
        if not staff:
            return None
        if staff.is_manager:
            return 'manager'
        if staff.is_waiter:
            return 'waiter'
        if staff.is_kitchen:
            return 'kitchen'
        return None
