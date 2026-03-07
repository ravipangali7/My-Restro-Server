from rest_framework import serializers
from django.conf import settings
from django.utils.text import slugify
from .models import (
    User,
    Staff,
    Restaurant,
    ShareholderWithdrawal,
    QrStandOrder,
    Transaction,
    SuperSetting,
    BulkNotification,
    Customer,
    Vendor,
    Unit,
    Category,
    Product,
    ProductVariant,
    ProductRawMaterial,
    RawMaterial,
    ComboSet,
    Attendance,
    Feedback,
)


def _build_media_url(request, path):
    if not path:
        return None
    if request and request.build_absolute_uri:
        base = request.build_absolute_uri('/').rstrip('/')
        return f"{base}{path}" if path.startswith('/') else f"{base}/{path}"
    return path


class UserSerializer(serializers.ModelSerializer):
    """Safe user fields for API responses; no password. Includes image_url and last_login for profile/me.
    For restaurant staff, includes restaurant_id and staff_id so manager/waiter/kitchen can scope API calls."""
    staff_role = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    restaurant_id = serializers.SerializerMethodField()
    staff_id = serializers.SerializerMethodField()

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
            'restaurant_id',
            'staff_id',
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

    def get_restaurant_id(self, obj):
        staff = obj.staff_profiles.first()
        return staff.restaurant_id if staff else None

    def get_staff_id(self, obj):
        staff = obj.staff_profiles.first()
        return staff.pk if staff else None


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
        if self.context.get('for_shareholder'):
            validated_data['is_shareholder'] = True
            validated_data['is_owner'] = False
        else:
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
        request = self.context.get('request')
        if request and getattr(request.user, 'is_owner', False) and not request.user.is_superuser:
            validated_data['user'] = request.user
        validated_data.setdefault('is_open', False)
        slug = (validated_data.get('slug') or '').strip()
        if not slug and validated_data.get('name'):
            base_slug = slugify(validated_data['name'])
            slug = base_slug
            idx = 1
            while Restaurant.objects.filter(slug=slug).exists():
                slug = f'{base_slug}-{idx}'
                idx += 1
            validated_data['slug'] = slug
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


# --- BulkNotification (super admin) ---

class BulkNotificationRestaurantMinSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ['id', 'slug', 'name', 'phone', 'country_code', 'logo_url']

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.logo.url if hasattr(obj.logo, 'url') else str(obj.logo))


class BulkNotificationListSerializer(serializers.ModelSerializer):
    restaurant = BulkNotificationRestaurantMinSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = BulkNotification
        fields = [
            'id', 'restaurant', 'message', 'image_url', 'type',
            'sent_count', 'total_count', 'created_at', 'updated_at',
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class BulkNotificationDetailSerializer(serializers.ModelSerializer):
    restaurant = BulkNotificationRestaurantMinSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    receivers_expanded = serializers.SerializerMethodField()

    class Meta:
        model = BulkNotification
        fields = [
            'id', 'restaurant', 'message', 'image_url', 'type',
            'sent_count', 'total_count', 'receivers', 'receivers_expanded',
            'created_at', 'updated_at',
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))

    def get_receivers_expanded(self, obj):
        request = self.context.get('request')
        expanded = []
        receivers = obj.receivers or []
        for r in receivers:
            if not isinstance(r, dict):
                continue
            rtype = (r.get('type') or '').strip().lower()
            rid = r.get('id')
            if rid is None:
                continue
            entry = {'type': rtype, 'id': rid, 'name': '', 'country_code': '', 'phone': '', 'image_url': None}
            try:
                if rtype == 'restaurant':
                    rest = Restaurant.objects.filter(pk=rid).first()
                    if rest:
                        entry['name'] = rest.name or ''
                        entry['country_code'] = rest.country_code or ''
                        entry['phone'] = rest.phone or ''
                        if rest.logo:
                            entry['image_url'] = _build_media_url(
                                request, rest.logo.url if hasattr(rest.logo, 'url') else str(rest.logo)
                            )
                elif rtype in ('owner', 'shareholder'):
                    user = User.objects.filter(pk=rid, is_owner=True).first()
                    if user:
                        entry['name'] = user.name or ''
                        entry['country_code'] = user.country_code or ''
                        entry['phone'] = user.phone or ''
                        if user.image:
                            entry['image_url'] = _build_media_url(
                                request, user.image.url if hasattr(user.image, 'url') else str(user.image)
                            )
                elif rtype == 'customer':
                    cust = Customer.objects.filter(pk=rid).first()
                    if cust:
                        entry['name'] = cust.name or ''
                        entry['country_code'] = cust.country_code or ''
                        entry['phone'] = cust.phone or ''
                elif rtype == 'vendor':
                    vendor = Vendor.objects.filter(pk=rid).first()
                    if vendor:
                        entry['name'] = vendor.name or ''
                        entry['country_code'] = vendor.country_code or ''
                        entry['phone'] = vendor.phone or ''
                        if vendor.image:
                            entry['image_url'] = _build_media_url(
                                request, vendor.image.url if hasattr(vendor.image, 'url') else str(vendor.image)
                            )
            except Exception:
                pass
            expanded.append(entry)
        return expanded


class BulkNotificationCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkNotification
        fields = ['restaurant', 'message', 'type', 'receivers', 'image']

    def validate_receivers(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('receivers must be a list.')
        for r in value:
            if not isinstance(r, dict) or 'type' not in r or 'id' not in r:
                raise serializers.ValidationError('Each receiver must have type and id.')
            t = (r.get('type') or '').strip().lower()
            if t not in ('restaurant', 'owner', 'customer', 'shareholder', 'vendor'):
                raise serializers.ValidationError(f'Invalid receiver type: {t}')
        request = self.context.get('request')
        if request and getattr(request.user, 'is_owner', False) and not getattr(request.user, 'is_superuser', False):
            for r in value:
                t = (r.get('type') or '').strip().lower()
                if t in ('owner', 'shareholder'):
                    raise serializers.ValidationError(
                        'Owners cannot send notifications to Owners or Shareholders.'
                    )
        return value

    def validate_type(self, value):
        v = (value or '').strip().lower()
        if v not in ('sms', 'whatsapp'):
            raise serializers.ValidationError('type must be sms or whatsapp.')
        return v


class CustomerListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ['id', 'name', 'phone', 'country_code', 'image_url', 'created_at']

    def get_image_url(self, obj):
        return None


# --- Owner-scoped list serializers ---

class OwnerStaffListSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='user.name', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    country_code = serializers.CharField(source='user.country_code', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    restaurant_id = serializers.IntegerField(source='restaurant.id', read_only=True)
    role = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    user_image_url = serializers.SerializerMethodField()
    assigned_table_ids = serializers.SerializerMethodField()
    attendance_days = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = [
            'id', 'name', 'phone', 'country_code', 'restaurant_id', 'restaurant_name',
            'role', 'per_day_salary', 'to_pay', 'to_receive', 'is_suspend',
            'is_active', 'created_at', 'user_image_url', 'assigned_table_ids', 'attendance_days',
        ]

    def get_role(self, obj):
        if obj.is_manager:
            return 'manager'
        if obj.is_waiter:
            return 'waiter'
        if obj.is_kitchen:
            return 'kitchen'
        return obj.designation or 'staff'

    def get_is_active(self, obj):
        return not obj.is_suspend

    def get_user_image_url(self, obj):
        if not obj.user or not obj.user.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.user.image.url if hasattr(obj.user.image, 'url') else str(obj.user.image))

    def get_assigned_table_ids(self, obj):
        if not hasattr(obj, 'assigned_tables'):
            return []
        return list(obj.assigned_tables.values_list('id', flat=True))

    def get_attendance_days(self, obj):
        return getattr(obj, 'attendance_days', None)


class OwnerStaffCreateUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=['manager', 'waiter', 'kitchen'], write_only=True, required=False)
    monthly_salary = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0)
    assigned_tables = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)

    class Meta:
        model = Staff
        fields = ['restaurant', 'user', 'role', 'designation', 'monthly_salary', 'per_day_salary', 'assigned_tables', 'joined_at']

    def validate_restaurant(self, value):
        request = self.context.get('request')
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None:
            if not request.user.is_superuser and value.id not in owner_ids:
                raise serializers.ValidationError('You can only add staff to restaurants you manage.')
            return value
        if not request:
            return value
        owner_ids = list(Restaurant.objects.filter(user=request.user).values_list('id', flat=True))
        if not request.user.is_superuser and value.id not in owner_ids:
            raise serializers.ValidationError('You can only add staff to your own restaurants.')
        return value

    def validate_user(self, value):
        instance = self.instance
        if instance is not None and instance.user_id == value.id:
            return value
        return value

    def validate(self, attrs):
        from decimal import Decimal
        monthly = attrs.pop('monthly_salary', None)
        per_day = attrs.get('per_day_salary')
        if monthly is not None and monthly != '':
            attrs['per_day_salary'] = (Decimal(str(monthly)) / 30).quantize(Decimal('0.01'))
            attrs['salary'] = Decimal(str(monthly))
            attrs['salary_type'] = 'monthly'
        elif per_day is not None and per_day != '':
            attrs['salary'] = Decimal('0')
            attrs['salary_type'] = 'per_day'
        elif not self.partial:
            attrs.setdefault('per_day_salary', Decimal('0'))
            attrs.setdefault('salary_type', 'per_day')
            attrs.setdefault('salary', Decimal('0'))
        role = attrs.pop('role', None)
        if role:
            attrs['is_manager'] = role == 'manager'
            attrs['is_waiter'] = role == 'waiter'
            attrs['is_kitchen'] = role == 'kitchen'
            if not attrs.get('designation'):
                attrs['designation'] = role
        if not self.instance:
            restaurant = attrs.get('restaurant')
            user = attrs.get('user')
            if restaurant and user and Staff.objects.filter(restaurant=restaurant, user=user).exists():
                raise serializers.ValidationError('This user is already staff at this restaurant.')
        return attrs

    def create(self, validated_data):
        assigned_table_ids = validated_data.pop('assigned_tables', [])
        instance = super().create(validated_data)
        if assigned_table_ids:
            instance.assigned_tables.set(assigned_table_ids)
        user = instance.user
        user.is_restaurant_staff = True
        user.save(update_fields=['is_restaurant_staff'])
        return instance

    def update(self, instance, validated_data):
        assigned_table_ids = validated_data.pop('assigned_tables', None)
        instance = super().update(instance, validated_data)
        if assigned_table_ids is not None:
            instance.assigned_tables.set(assigned_table_ids)
        return instance


# --- Attendance (owner/manager) ---

class AttendanceListSerializer(serializers.ModelSerializer):
    staff_id = serializers.IntegerField(source='staff.id', read_only=True)
    staff_name = serializers.CharField(source='staff.user.name', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'staff_id', 'staff_name', 'status', 'leave_reason', 'created_at']


class AttendanceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ['status', 'leave_reason']

    def validate_status(self, value):
        if value and value.lower() not in ('present', 'absent', 'leave'):
            raise serializers.ValidationError('Status must be present, absent, or leave.')
        return value.lower() if value else value


# --- Feedback (owner/manager) ---

class FeedbackListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True, allow_null=True)

    class Meta:
        model = Feedback
        fields = ['id', 'customer_name', 'order_id', 'rating', 'review', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('customer_name') is None or data.get('customer_name') == '':
            data['customer_name'] = 'Anonymous'
        data['comment'] = data.get('review', '')
        return data


class FeedbackDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True, allow_null=True)

    class Meta:
        model = Feedback
        fields = ['id', 'customer_name', 'order_id', 'rating', 'review', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('customer_name') is None or data.get('customer_name') == '':
            data['customer_name'] = 'Anonymous'
        data['comment'] = data.get('review', '')
        return data


class OwnerVendorListSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    restaurant_id = serializers.IntegerField(source='restaurant.id', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['id', 'name', 'phone', 'country_code', 'restaurant_id', 'restaurant_name', 'image_url', 'to_pay', 'to_receive', 'created_at']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class OwnerVendorCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['name', 'phone', 'country_code', 'restaurant', 'image']

    def validate_restaurant(self, value):
        request = self.context.get('request')
        if not request:
            return value
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.id not in owner_ids:
            raise serializers.ValidationError('You can only add vendors to your own restaurants.')
        if owner_ids is None and not request.user.is_superuser:
            owner_ids = list(Restaurant.objects.filter(user=request.user).values_list('id', flat=True))
            if value.id not in owner_ids:
                raise serializers.ValidationError('You can only add vendors to your own restaurants.')
        return value


# --- Units (owner/manager scoped) ---

class UnitListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ['id', 'name', 'symbol', 'restaurant', 'created_at', 'updated_at']


class UnitCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ['name', 'symbol', 'restaurant']

    def validate_restaurant(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.id not in owner_ids:
            raise serializers.ValidationError('Restaurant not in your scope.')
        return value


# --- Categories (owner/manager scoped) ---

class CategoryListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'image', 'image_url', 'restaurant', 'item_count', 'created_at', 'updated_at']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class CategoryCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['name', 'image', 'restaurant']

    def validate_restaurant(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.id not in owner_ids:
            raise serializers.ValidationError('Restaurant not in your scope.')
        return value


# --- Products (owner/manager scoped, with variants and raw_material_links) ---

class ProductVariantNestedSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_symbol = serializers.CharField(source='unit.symbol', read_only=True)

    class Meta:
        model = ProductVariant
        fields = ['id', 'unit', 'unit_name', 'unit_symbol', 'price', 'discount_type', 'discount', 'created_at', 'updated_at']


class ProductRawMaterialNestedSerializer(serializers.ModelSerializer):
    raw_material_name = serializers.CharField(source='raw_material.name', read_only=True)

    class Meta:
        model = ProductRawMaterial
        fields = ['id', 'raw_material', 'raw_material_name', 'raw_material_quantity', 'product_variant', 'image', 'created_at', 'updated_at']


class ProductListSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    variants = ProductVariantNestedSerializer(many=True, read_only=True)
    raw_material_links_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'restaurant', 'category', 'category_id', 'category_name',
            'image', 'image_url', 'is_active', 'dish_type',
            'variants', 'raw_material_links_count',
            'created_at', 'updated_at',
        ]

    def get_raw_material_links_count(self, obj):
        return getattr(obj, 'raw_material_links_count', obj.raw_material_links.count())

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class ProductDetailSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    variants = ProductVariantNestedSerializer(many=True, read_only=True)
    raw_material_links = ProductRawMaterialNestedSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'restaurant', 'category', 'category_id', 'category_name',
            'image', 'image_url', 'is_active', 'dish_type',
            'variants', 'raw_material_links',
            'created_at', 'updated_at',
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class ProductVariantWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'unit', 'price', 'discount_type', 'discount']

    def validate_unit(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.restaurant_id not in owner_ids:
            raise serializers.ValidationError('Unit not in your scope.')
        return value


class ProductRawMaterialWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductRawMaterial
        fields = ['id', 'raw_material', 'raw_material_quantity', 'product_variant', 'image']

    def validate_raw_material(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.restaurant_id not in owner_ids:
            raise serializers.ValidationError('Raw material not in your scope.')
        return value

    def validate_product_variant(self, value):
        if value is None:
            return value
        product = self.context.get('product')
        if product and value.product_id != product.id:
            raise serializers.ValidationError('Variant must belong to this product.')
        return value


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    variants = ProductVariantWriteSerializer(many=True, required=False)
    raw_material_links = ProductRawMaterialWriteSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = ['name', 'restaurant', 'category', 'image', 'is_active', 'dish_type', 'variants', 'raw_material_links']

    def validate_category(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.restaurant_id not in owner_ids:
            raise serializers.ValidationError('Category not in your scope.')
        return value

    def validate_restaurant(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.id not in owner_ids:
            raise serializers.ValidationError('Restaurant not in your scope.')
        return value

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        raw_material_links_data = validated_data.pop('raw_material_links', [])
        product = Product.objects.create(**validated_data)
        for v in variants_data:
            ProductVariant.objects.create(product=product, **v)
        for r in raw_material_links_data:
            ProductRawMaterial.objects.create(
                restaurant=product.restaurant,
                product=product,
                raw_material=r['raw_material'],
                raw_material_quantity=r['raw_material_quantity'],
                product_variant=r.get('product_variant'),
                image=r.get('image'),
            )
        return product

    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        raw_material_links_data = validated_data.pop('raw_material_links', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if variants_data is not None:
            ProductVariant.objects.filter(product=instance).delete()
            for v in variants_data:
                ProductVariant.objects.create(product=instance, **v)
        if raw_material_links_data is not None:
            ProductRawMaterial.objects.filter(product=instance).delete()
            for r in raw_material_links_data:
                ProductRawMaterial.objects.create(
                    restaurant=instance.restaurant,
                    product=instance,
                    raw_material=r['raw_material'],
                    raw_material_quantity=r['raw_material_quantity'],
                    product_variant=r.get('product_variant'),
                    image=r.get('image'),
                )
        return instance


# --- Combos (owner/manager scoped) ---

class ComboSetListSerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    product_names = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ComboSet
        fields = ['id', 'name', 'description', 'image', 'image_url', 'restaurant', 'price', 'products_count', 'product_names', 'created_at', 'updated_at']

    def get_products_count(self, obj):
        return getattr(obj, 'products_count', obj.products.count())

    def get_product_names(self, obj):
        return list(obj.products.values_list('name', flat=True)[:10])

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class ComboSetDetailSerializer(serializers.ModelSerializer):
    product_ids = serializers.SerializerMethodField()
    product_names = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ComboSet
        fields = ['id', 'name', 'description', 'image', 'image_url', 'restaurant', 'price', 'product_ids', 'product_names', 'created_at', 'updated_at']

    def get_product_ids(self, obj):
        return list(obj.products.values_list('id', flat=True))

    def get_product_names(self, obj):
        return list(obj.products.values_list('name', flat=True))

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return _build_media_url(request, obj.image.url if hasattr(obj.image, 'url') else str(obj.image))


class ComboSetCreateUpdateSerializer(serializers.ModelSerializer):
    products = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    class Meta:
        model = ComboSet
        fields = ['name', 'description', 'image', 'restaurant', 'price', 'products']

    def validate_restaurant(self, value):
        owner_ids = self.context.get('owner_ids')
        if owner_ids is not None and value.id not in owner_ids:
            raise serializers.ValidationError('Restaurant not in your scope.')
        return value

    def validate_products(self, value):
        owner_ids = self.context.get('owner_ids')
        if not owner_ids:
            return value
        from .models import Product
        valid = set(Product.objects.filter(id__in=value, restaurant_id__in=owner_ids).values_list('id', flat=True))
        if len(value) != len([i for i in value if i in valid]):
            raise serializers.ValidationError('Some product IDs are not in your scope.')
        return value

    def create(self, validated_data):
        product_ids = validated_data.pop('products', [])
        combo = ComboSet.objects.create(**validated_data)
        if product_ids:
            combo.products.set(product_ids)
        return combo

    def update(self, instance, validated_data):
        product_ids = validated_data.pop('products', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if product_ids is not None:
            instance.products.set(product_ids)
        return instance
