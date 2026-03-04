from rest_framework import serializers
from django.conf import settings
from .models import User, Staff, Restaurant, ShareholderWithdrawal, QrStandOrder, Transaction, SuperSetting


def _build_media_url(request, path):
    if not path:
        return None
    if request and request.build_absolute_uri:
        base = request.build_absolute_uri('/').rstrip('/')
        return f"{base}{path}" if path.startswith('/') else f"{base}/{path}"
    return path


class UserSerializer(serializers.ModelSerializer):
    """Safe user fields for API responses; no password. Includes image_url and last_login for profile/me."""
    staff_role = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

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
            'last_login',
            'image_url',
        ]
        read_only_fields = fields

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))

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


# --- SuperSetting (super admin) ---

class SuperSettingSerializer(serializers.ModelSerializer):
    """Read-only representation of SuperSetting for GET."""
    class Meta:
        model = SuperSetting
        fields = [
            'id',
            'per_qr_stand_price',
            'subscription_fee_per_month',
            'per_transaction_fee',
            'due_threshold',
            'is_subscription_fee',
            'is_whatsapp_usgage',
            'whatsapp_per_usgage',
            'share_distribution_day',
            'ug_api',
            'balance',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class SuperSettingUpdateSerializer(serializers.ModelSerializer):
    """Editable fields for PATCH; balance and timestamps are read-only."""
    class Meta:
        model = SuperSetting
        fields = [
            'per_qr_stand_price',
            'subscription_fee_per_month',
            'per_transaction_fee',
            'due_threshold',
            'is_subscription_fee',
            'is_whatsapp_usgage',
            'whatsapp_per_usgage',
            'share_distribution_day',
            'ug_api',
        ]

    def validate_share_distribution_day(self, value):
        if value is not None and (value < 1 or value > 31):
            raise serializers.ValidationError('Must be between 1 and 31.')
        return value


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
    owner_name = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'slug', 'name', 'phone', 'country_code', 'address',
            'balance', 'due_balance', 'subscription_start', 'subscription_end',
            'is_open', 'created_at', 'owner_name', 'logo_url', 'is_active', 'user',
        ]

    def get_owner_name(self, obj):
        try:
            user = getattr(obj, 'user', None)
            return (user.name if user else '') or ''
        except Exception:
            return ''

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        try:
            request = self.context.get('request')
            url = obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo)
            return _build_media_url(request, url)
        except Exception:
            return None

    def get_is_active(self, obj):
        return getattr(obj, 'is_open', False)


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


# --- Transaction ---

class TransactionRestaurantMinSerializer(serializers.ModelSerializer):
    """Minimal restaurant + owner for transaction list row."""
    owner_name = serializers.SerializerMethodField()
    owner_id = serializers.IntegerField(source='user_id', read_only=True)
    owner_phone = serializers.SerializerMethodField()
    owner_country_code = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ['id', 'slug', 'name', 'owner_id', 'owner_name', 'owner_phone', 'owner_country_code', 'logo_url']

    def get_owner_name(self, obj):
        user = getattr(obj, 'user', None)
        return (user.name if user else '') or ''

    def get_owner_phone(self, obj):
        user = getattr(obj, 'user', None)
        return (user.phone if user else '') or ''

    def get_owner_country_code(self, obj):
        user = getattr(obj, 'user', None)
        return (user.country_code if user else '') or ''

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))


class TransactionSerializer(serializers.ModelSerializer):
    """Transaction list item."""
    reference = serializers.SerializerMethodField()
    restaurant = TransactionRestaurantMinSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'reference', 'restaurant', 'amount', 'payment_status', 'transaction_type', 'category',
            'utr', 'vpa', 'payer_name', 'remarks', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_reference(self, obj):
        return obj.utr or str(obj.id)


class TransactionDetailSerializer(serializers.ModelSerializer):
    """Transaction detail for view page; includes full restaurant with owner."""
    reference = serializers.SerializerMethodField()
    restaurant = RestaurantDetailSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'reference', 'restaurant', 'amount', 'payment_status', 'transaction_type', 'category',
            'utr', 'vpa', 'payer_name', 'remarks', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_reference(self, obj):
        return obj.utr or str(obj.id)


# --- Shareholder withdrawal ---

class ShareholderWithdrawalSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)

    class Meta:
        model = ShareholderWithdrawal
        fields = ['id', 'user', 'user_name', 'amount', 'status', 'remarks', 'reject_reason', 'created_at']


class ShareholderWithdrawalListSerializer(serializers.ModelSerializer):
    """Withdrawal list with user details for table row."""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_country_code = serializers.CharField(source='user.country_code', read_only=True)
    user_balance = serializers.DecimalField(source='user.balance', max_digits=12, decimal_places=2, read_only=True)
    user_share_percentage = serializers.DecimalField(source='user.share_percentage', max_digits=5, decimal_places=2, read_only=True)
    user_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ShareholderWithdrawal
        fields = [
            'id', 'user', 'user_name', 'user_phone', 'user_country_code',
            'user_balance', 'user_share_percentage', 'user_image_url',
            'amount', 'status', 'remarks', 'reject_reason', 'created_at',
        ]

    def get_user_image_url(self, obj):
        user = getattr(obj, 'user', None)
        if not user or not user.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, user.image.url if hasattr(user.image, 'url') else str(user.image))


class ShareholderWithdrawalCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShareholderWithdrawal
        fields = ['user', 'amount', 'remarks']


class ShareholderWithdrawalDetailSerializer(serializers.ModelSerializer):
    """Withdrawal detail with full user (owner) info for view page."""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user = OwnerSerializer(read_only=True)

    class Meta:
        model = ShareholderWithdrawal
        fields = ['id', 'user', 'user_name', 'amount', 'status', 'remarks', 'reject_reason', 'created_at', 'updated_at']


# --- QR Stand Order ---

class QrStandOrderRestaurantMinSerializer(serializers.ModelSerializer):
    """Minimal restaurant for QR stand order list/detail."""
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ['id', 'slug', 'name', 'phone', 'country_code', 'logo_url']

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))


class QrStandOrderListSerializer(serializers.ModelSerializer):
    restaurant = QrStandOrderRestaurantMinSerializer(read_only=True)

    class Meta:
        model = QrStandOrder
        fields = ['id', 'restaurant', 'quantity', 'total', 'status', 'payment_status', 'created_at']


class QrStandOrderDetailSerializer(serializers.ModelSerializer):
    restaurant = QrStandOrderRestaurantMinSerializer(read_only=True)

    class Meta:
        model = QrStandOrder
        fields = ['id', 'restaurant', 'quantity', 'total', 'status', 'payment_status', 'created_at', 'updated_at']


class QrStandOrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QrStandOrder
        fields = ['restaurant', 'quantity']

    def validate_quantity(self, value):
        if value is None or value < 1:
            raise serializers.ValidationError('Quantity must be at least 1.')
        return value

    def create(self, validated_data):
        from decimal import Decimal
        from .services import get_super_setting
        quantity = validated_data['quantity']
        ss = get_super_setting()
        price = (ss.per_qr_stand_price or Decimal('0'))
        total = Decimal(str(quantity)) * price
        validated_data['total'] = total
        return super().create(validated_data)


class QrStandOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = QrStandOrder
        fields = ['quantity', 'status']

    def validate_quantity(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError('Quantity must be at least 1.')
        return value

    def update(self, instance, validated_data):
        quantity = validated_data.get('quantity')
        if quantity is not None:
            from decimal import Decimal
            from .services import get_super_setting
            ss = get_super_setting()
            price = (ss.per_qr_stand_price or Decimal('0'))
            validated_data['total'] = Decimal(str(quantity)) * price
        return super().update(instance, validated_data)
