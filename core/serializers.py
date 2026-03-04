from rest_framework import serializers
from django.conf import settings
from .models import User, Staff, Restaurant, ShareholderWithdrawal, QrStandOrder


def _build_media_url(request, path):
    if not path:
        return None
    if request and request.build_absolute_uri:
        base = request.build_absolute_uri('/').rstrip('/')
        return f"{base}{path}" if path.startswith('/') else f"{base}/{path}"
    return path


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


# --- Owner (User with is_owner=True) ---

class OwnerSerializer(serializers.ModelSerializer):
    """Owner list/detail read serializer; includes image and kyc_document URLs."""
    staff_role = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    kyc_document_url = serializers.SerializerMethodField()
    reject_reason = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'name', 'phone', 'country_code', 'is_owner', 'staff_role',
            'kyc_status', 'reject_reason', 'kyc_document_url', 'image_url',
            'is_shareholder', 'share_percentage', 'balance', 'due_balance', 'created_at',
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

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))

    def get_kyc_document_url(self, obj):
        if not obj.kyc_document:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.kyc_document.url if hasattr(obj.kyc_document, 'url') else str(obj.kyc_document))


class OwnerCreateUpdateSerializer(serializers.ModelSerializer):
    """Create/update owner; accepts password, image, kyc_document. Also used for shareholder (share_percentage)."""
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'name', 'country_code', 'phone', 'password', 'image', 'is_owner',
            'balance', 'due_balance', 'kyc_status', 'reject_reason', 'kyc_document',
            'share_percentage', 'is_shareholder',
        ]

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        validated_data.setdefault('is_owner', True)
        # AbstractUser requires unique username; use country_code+phone
        if 'username' not in validated_data:
            validated_data['username'] = (validated_data.get('country_code') or '') + (validated_data.get('phone') or '')
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password is not None and password:
            instance.set_password(password)
        instance.save()
        return instance


class OwnerDetailSerializer(OwnerSerializer):
    """Owner detail for view page; includes restaurants and qr_stand_orders."""
    restaurants = serializers.SerializerMethodField()
    qr_stand_orders = serializers.SerializerMethodField()

    class Meta(OwnerSerializer.Meta):
        fields = OwnerSerializer.Meta.fields + ['restaurants', 'qr_stand_orders']

    def get_restaurants(self, obj):
        qs = obj.restaurants.all().order_by('name')
        return RestaurantMinSerializer(qs, many=True, context=self.context).data

    def get_qr_stand_orders(self, obj):
        out = []
        sn = 1
        for rest in obj.restaurants.all():
            for qo in rest.qr_stand_orders.all().order_by('-created_at')[:50]:
                out.append({
                    'sn': sn,
                    'owner': obj.name,
                    'amount': str(qo.total),
                    'status': qo.status,
                })
                sn += 1
        return out


# --- Restaurant (minimal for owner detail) ---

class RestaurantMinSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'slug', 'name', 'phone', 'country_code', 'address',
            'balance', 'due_balance', 'subscription_start', 'subscription_end', 'logo_url',
        ]

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))


# --- Restaurant ---

class RestaurantListSerializer(serializers.ModelSerializer):
    """Restaurant list item; include owner name and logo URL."""
    owner_name = serializers.CharField(source='user.name', read_only=True)
    logo_url = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'slug', 'name', 'phone', 'country_code', 'address',
            'balance', 'due_balance', 'subscription_start', 'subscription_end',
            'is_open', 'created_at', 'owner_name', 'logo_url', 'user_id',
        ]

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))

    def get_is_active(self, obj):
        return obj.is_open


class RestaurantDetailSerializer(serializers.ModelSerializer):
    """Restaurant detail for view page; include owner and logo URL."""
    owner = OwnerSerializer(source='user', read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'slug', 'name', 'phone', 'country_code', 'address',
            'latitude', 'longitude', 'balance', 'due_balance', 'ug_api',
            'subscription_start', 'subscription_end', 'is_open', 'created_at',
            'logo_url', 'owner',
        ]

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))


class RestaurantCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = [
            'user', 'slug', 'name', 'phone', 'country_code', 'address',
            'latitude', 'longitude', 'logo', 'ug_api',
            'balance', 'due_balance', 'subscription_start', 'subscription_end', 'is_open',
        ]

    def create(self, validated_data):
        validated_data.setdefault('is_open', False)
        return super().create(validated_data)


# --- Shareholder withdrawal ---

class ShareholderWithdrawalSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)

    class Meta:
        model = ShareholderWithdrawal
        fields = ['id', 'user', 'user_name', 'amount', 'status', 'remarks', 'reject_reason', 'created_at']
