from django.db import models
from django.contrib.auth.models import AbstractUser
from decimal import Decimal


# --- Choice constants ---

class DiscountType(models.TextChoices):
    FLAT = 'flat', 'Flat'
    PERCENTAGE = 'percentage', 'Percentage'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    SUCCESS = 'success', 'Success'
    PAID = 'paid', 'Paid'


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Cash'
    E_WALLET = 'e_wallet', 'E Wallet'
    BANK = 'bank', 'Bank'


class KycStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class OrderType(models.TextChoices):
    TABLE = 'table', 'Table'
    PACKING = 'packing', 'Packing'
    DELIVERY = 'delivery', 'Delivery'


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    RUNNING = 'running', 'Running'
    READY = 'ready', 'Ready'
    SERVED = 'served', 'Served'
    REJECTED = 'rejected', 'Rejected'


class DishType(models.TextChoices):
    VEG = 'veg', 'Veg'
    NON_VEG = 'non_veg', 'Non-Veg'


class TransactionType(models.TextChoices):
    IN = 'in', 'In'
    OUT = 'out', 'Out'


class TransactionCategory(models.TextChoices):
    TRANSACTION_FEE = 'transaction_fee', 'Transaction Fee'
    SUBSCRIPTION_FEE = 'subscription_fee', 'Subscription Fee'
    WHATSAPP_USAGE = 'whatsapp_usage', 'WhatsApp Usage'
    QR_STAND_ORDER = 'qr_stand_order', 'QR Stand Order'
    SHARE_DISTRIBUTION = 'share_distribution', 'Share Distribution'
    SHARE_WITHDRAWAL = 'share_withdrawal', 'Share Withdrawal'
    DUE_PAID = 'due_paid', 'Due Paid'
    PAID_RECORD = 'paid_record', 'Paid Record'
    RECEIVED_RECORD = 'received_record', 'Received Record'


class StockLogType(models.TextChoices):
    IN = 'in', 'In'
    OUT = 'out', 'Out'


class AttendanceStatus(models.TextChoices):
    PRESENT = 'present', 'Present'
    ABSENT = 'absent', 'Absent'
    LEAVE = 'leave', 'Leave'


class SalaryType(models.TextChoices):
    PER_DAY = 'per_day', 'Per Day'
    MONTHLY = 'monthly', 'Monthly'


class QrStandOrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    SHIPPED = 'shipped', 'Shipped'
    DELIVERED = 'delivered', 'Delivered'


class WithdrawalStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECT = 'reject', 'Reject'


class BulkNotificationType(models.TextChoices):
    SMS = 'sms', 'SMS'
    WHATSAPP = 'whatsapp', 'WhatsApp'


class WaiterCallStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMPLETED = 'completed', 'Completed'


class DeliveryStatus(models.TextChoices):
    ACCEPTED = 'accepted', 'Accepted'
    RIDER_ASSIGNED = 'rider_assigned', 'Rider Assigned'
    RIDER_PICKED_UP = 'rider_picked_up', 'Rider Picked Up'
    ON_THE_WAY = 'on_the_way', 'On The Way'
    DELIVERED = 'delivered', 'Delivered'
    RETURNED = 'returned', 'Returned'


class RiderSource(models.TextChoices):
    IN_HOUSE = 'in_house', 'In House'
    PATHAO = 'pathao', 'Pathao'
    YANGO = 'yango', 'Yango'


# --- Models ---

class User(AbstractUser):
    """Custom user; id and password from AbstractUser."""
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20)
    country_code = models.CharField(max_length=10)
    image = models.ImageField(upload_to='users/', blank=True, null=True)
    is_owner = models.BooleanField(default=False)
    is_restaurant_staff = models.BooleanField(default=False)
    is_kitchen = models.BooleanField(default=False)
    kyc_status = models.CharField(
        max_length=20, choices=KycStatus.choices, default=KycStatus.PENDING
    )
    reject_reason = models.TextField(blank=True)
    kyc_document = models.FileField(upload_to='kyc/', blank=True, null=True)
    is_shareholder = models.BooleanField(default=False)
    share_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    due_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    fcm_token = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'id'  # Login uses (country_code, phone) via custom auth

    class Meta:
        db_table = 'core_user'
        constraints = [
            models.UniqueConstraint(
                fields=['country_code', 'phone'],
                name='unique_user_country_phone',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.name and (self.first_name or self.last_name):
            self.name = f'{self.first_name or ""} {self.last_name or ""}'.strip()
        super().save(*args, **kwargs)


class Customer(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='customer_profile',
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    country_code = models.CharField(max_length=10)
    address = models.TextField(blank=True)
    password = models.CharField(max_length=128, default='!')  # hashed; '!' = unusable for existing rows
    fcm_token = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_customer'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['country_code', 'phone'],
                name='unique_customer_country_phone',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.phone})'


class CustomerToken(models.Model):
    """Token for customer auth; separate from DRF Token (User)."""
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='tokens'
    )
    key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_customer_token'
        ordering = ['-created_at']

    def __str__(self):
        return f'Token for {self.customer}'


class Restaurant(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='restaurants'
    )
    slug = models.SlugField(unique=True, max_length=100)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='restaurants/', blank=True, null=True)
    address = models.TextField(blank=True)
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Tax percentage applied on subtotal for invoice (e.g. 13 for 13%%)'
    )
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text='Pickup point for delivery'
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text='Pickup point for delivery'
    )
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    due_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    ug_api = models.CharField(max_length=255, blank=True, null=True)
    esewa_merchant_id = models.CharField(max_length=255, blank=True, null=True, help_text='Esewa merchant ID for online payment QR')
    subscription_start = models.DateField(null=True, blank=True)
    subscription_end = models.DateField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    # System active/inactive; if False, hidden from public list, QR/menu disabled, new orders blocked
    is_restaurant = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_restaurant'
        ordering = ['name']

    def __str__(self):
        return self.name


class CustomerRestaurant(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='restaurant_links'
    )
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='customer_links'
    )
    to_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    to_receive = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_customer_restaurant'
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'restaurant'],
                name='unique_customer_restaurant'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.customer} @ {self.restaurant}'


class Vendor(models.Model):
    name = models.CharField(max_length=255)
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='vendors'
    )
    role = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=10, blank=True)
    image = models.ImageField(upload_to='vendors/', blank=True, null=True)
    to_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    to_receive = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_vendor'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.restaurant.name})'


class Unit(models.Model):
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=20, blank=True)
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='units'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_unit'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.symbol or "-"})'


class Category(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='categories'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_category'
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='products'
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='products'
    )
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    dish_type = models.CharField(
        max_length=20, choices=DishType.choices, default=DishType.VEG
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_product'
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='variants'
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name='product_variants'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(
        max_length=20, choices=DiscountType.choices, blank=True
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_product_variant'
        ordering = ['product', 'unit']

    def __str__(self):
        return f'{self.product.name} ({self.unit.symbol or self.unit.name})'

    def get_final_price(self):
        """Compute price after discount for OrderItem total and stock calculations."""
        if not self.discount:
            return self.price
        if self.discount_type == DiscountType.FLAT:
            return max(Decimal('0'), self.price - self.discount)
        if self.discount_type == DiscountType.PERCENTAGE:
            return self.price * (Decimal('100') - self.discount) / Decimal('100')
        return self.price


class RawMaterial(models.Model):
    name = models.CharField(max_length=255)
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='raw_materials'
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name='raw_materials',
        null=True, blank=True
    )
    unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name='raw_materials'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    stock = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0')
    )
    min_stock = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0'), null=True, blank=True
    )
    image = models.ImageField(upload_to='raw_materials/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_raw_material'
        ordering = ['name']

    def __str__(self):
        return self.name


class ProductRawMaterial(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='product_raw_materials'
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='raw_material_links'
    )
    product_variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE,
        related_name='raw_material_links', null=True, blank=True
    )
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE, related_name='product_links'
    )
    raw_material_quantity = models.DecimalField(max_digits=12, decimal_places=4)
    image = models.ImageField(upload_to='recipe_mapping/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_product_raw_material'
        ordering = ['product', 'raw_material']

    def __str__(self):
        return f'{self.product.name} -> {self.raw_material.name}'


class ComboSet(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='combo_sets'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='combos/', blank=True, null=True)
    products = models.ManyToManyField(
        Product, related_name='combo_sets', blank=True
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_combo_set'
        ordering = ['name']

    def __str__(self):
        return self.name


class Table(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='tables'
    )
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(default=0)
    floor = models.CharField(max_length=50, blank=True)
    near_by = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_table'
        ordering = ['floor', 'name']

    def __str__(self):
        return f'{self.name} ({self.restaurant.name})'


class Staff(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='staffs'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='staff_profiles'
    )
    is_manager = models.BooleanField(default=False)
    is_waiter = models.BooleanField(default=False)
    designation = models.CharField(max_length=100, blank=True)
    joined_at = models.DateField(null=True, blank=True)
    salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    per_day_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    salary_type = models.CharField(
        max_length=20, choices=SalaryType.choices, default=SalaryType.PER_DAY
    )
    is_suspend = models.BooleanField(default=False)
    to_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    to_receive = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    assigned_tables = models.ManyToManyField(
        'Table', related_name='assigned_waiters', blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_staff'
        ordering = ['restaurant', 'user']
        constraints = [
            models.UniqueConstraint(
                fields=['restaurant', 'user'],
                name='unique_staff_restaurant_user'
            )
        ]

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} @ {self.restaurant.name}'


class Order(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='orders',
        null=True, blank=True
    )
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='orders'
    )
    table = models.ForeignKey(
        Table, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders'
    )
    order_type = models.CharField(
        max_length=20, choices=OrderType.choices, default=OrderType.TABLE
    )
    address = models.TextField(blank=True, null=True)
    delivery_lat = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text='Customer delivery location latitude'
    )
    delivery_lon = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text='Customer delivery location longitude'
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, blank=True
    )
    fcm_token = models.CharField(max_length=255, blank=True)
    waiter = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='served_orders'
    )
    people_for = models.PositiveIntegerField(default=1, null=True, blank=True)
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    service_charge = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=None,
        help_text='Order-level discount amount'
    )
    transaction_reference = models.CharField(max_length=255, blank=True, null=True, help_text='Online payment transaction ID (e.g. Esewa)')
    reject_reason = models.TextField(blank=True)
    table_number = models.CharField(max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_order'
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.id} ({self.restaurant.name})'


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='order_items',
        null=True, blank=True
    )
    product_variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name='order_items',
        null=True, blank=True
    )
    combo_set = models.ForeignKey(
        ComboSet, on_delete=models.CASCADE, related_name='order_items',
        null=True, blank=True
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_order_item'
        ordering = ['order', 'id']

    def __str__(self):
        return f'OrderItem #{self.id} (Order #{self.order_id})'


class Rider(models.Model):
    """In-house or third-party rider for delivery. Can be linked to User or standalone."""
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rider_deliveries'
    )
    is_available = models.BooleanField(default=True)
    last_lat = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    last_lon = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    last_updated = models.DateTimeField(null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=RiderSource.choices,
        default=RiderSource.IN_HOUSE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_rider'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.phone})'


class Delivery(models.Model):
    """One-to-one with Order for delivery orders. Tracks rider, location, ETA."""
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='delivery',
        primary_key=True
    )
    rider = models.ForeignKey(
        Rider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries'
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.ACCEPTED
    )
    pickup_lat = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    pickup_lon = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    delivery_lat = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    delivery_lon = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    rider_lat = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    rider_lon = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    distance_km = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    third_party_request_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_delivery'
        verbose_name_plural = 'Deliveries'

    def __str__(self):
        return f'Delivery for Order #{self.order_id}'


class Feedback(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='feedbacks'
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='feedbacks'
    )
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='feedbacks',
        null=True, blank=True
    )
    staff = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='feedbacks'
    )
    rating = models.PositiveSmallIntegerField(default=0)
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_feedback'
        ordering = ['-created_at']

    def __str__(self):
        return f'Feedback #{self.id} ({self.rating})'


class WaiterCall(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='waiter_calls'
    )
    table = models.ForeignKey(
        Table, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='waiter_calls'
    )
    table_number = models.CharField(max_length=64, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=WaiterCallStatus.choices,
        default=WaiterCallStatus.PENDING
    )
    assigned_to = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='waiter_calls'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_waiter_call'
        ordering = ['-created_at']

    def __str__(self):
        return f'WaiterCall #{self.id} ({self.restaurant.name})'


class Purchase(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='purchases'
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    discount_type = models.CharField(
        max_length=20, choices=DiscountType.choices, blank=True
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_purchase'
        ordering = ['-created_at']

    def __str__(self):
        return f'Purchase #{self.id} ({self.restaurant.name})'

    def save(self, *args, **kwargs):
        self.total = self.compute_total()
        super().save(*args, **kwargs)

    def compute_total(self):
        """Compute total from subtotal and discount."""
        if not self.discount:
            return self.subtotal
        if self.discount_type == DiscountType.FLAT:
            return max(Decimal('0'), self.subtotal - self.discount)
        if self.discount_type == DiscountType.PERCENTAGE:
            return self.subtotal * (Decimal('100') - self.discount) / Decimal('100')
        return self.subtotal


class PurchaseItem(models.Model):
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE, related_name='purchase_items'
    )
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='items'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_purchase_item'
        ordering = ['purchase', 'id']

    def __str__(self):
        return f'{self.raw_material.name} x {self.quantity}'


class Expenses(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='expenses'
    )
    name = models.CharField(max_length=255)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses'
    )
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.ImageField(upload_to='expenses/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_expenses'
        verbose_name_plural = 'Expenses'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.restaurant.name})'


class PaidRecord(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='paid_records'
    )
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_records'
    )
    purchase = models.ForeignKey(
        Purchase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_records'
    )
    expenses = models.ForeignKey(
        Expenses, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_records'
    )
    staff = models.ForeignKey(
        Staff, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_records'
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, blank=True
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_paid_record'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.amount}'


class ReceivedRecord(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='received_records'
    )
    name = models.CharField(max_length=255)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_records'
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='received_records'
    )
    remarks = models.TextField(blank=True)
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_received_record'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.amount}'


class Transaction(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='transactions',
        null=True, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, blank=True
    )
    remarks = models.TextField(blank=True)
    utr = models.CharField(max_length=100, blank=True)
    vpa = models.CharField(max_length=100, blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    bank_id = models.CharField(max_length=100, blank=True)
    transaction_type = models.CharField(
        max_length=10, choices=TransactionType.choices
    )
    category = models.CharField(
        max_length=30, choices=TransactionCategory.choices, blank=True
    )
    paid_record = models.ForeignKey(
        PaidRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions'
    )
    received_record = models.ForeignKey(
        ReceivedRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transactions'
    )
    is_system = models.BooleanField(default=False)
    ug_order_id = models.CharField(max_length=100, blank=True)
    ug_client_txn_id = models.CharField(max_length=100, blank=True)
    ug_payment_url = models.URLField(blank=True)
    ug_txn_date = models.DateTimeField(null=True, blank=True)
    ug_status = models.CharField(max_length=50, blank=True)
    ug_remarks = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    nepal_merchant_txn_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f'Transaction #{self.id} {self.transaction_type} {self.amount}'


class StockLog(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='stock_logs'
    )
    raw_material = models.ForeignKey(
        RawMaterial, on_delete=models.CASCADE, related_name='stock_logs',
        null=True, blank=True
    )
    type = models.CharField(max_length=10, choices=StockLogType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    purchase = models.ForeignKey(
        Purchase, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_logs'
    )
    purchase_item = models.ForeignKey(
        PurchaseItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_logs'
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_logs'
    )
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_logs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_stock_log'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.type} {self.quantity} ({self.raw_material or "?"})'


class Attendance(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='attendances'
    )
    date = models.DateField()
    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name='attendances'
    )
    status = models.CharField(
        max_length=20, choices=AttendanceStatus.choices
    )
    leave_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendance_records_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_attendance'
        ordering = ['-date', 'staff']
        constraints = [
            models.UniqueConstraint(
                fields=['restaurant', 'staff', 'date'],
                name='unique_attendance_restaurant_staff_date'
            )
        ]

    def __str__(self):
        return f'{self.staff} - {self.date} ({self.status})'


class SuperSetting(models.Model):
    per_qr_stand_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    subscription_fee_per_month = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    ug_api = models.CharField(max_length=255, blank=True, null=True)
    per_transaction_fee = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    is_subscription_fee = models.BooleanField(default=True)
    due_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    is_whatsapp_usgage = models.BooleanField(default=False)
    whatsapp_per_usgage = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'), null=True, blank=True
    )
    share_distribution_day = models.PositiveSmallIntegerField(null=True, blank=True)
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_super_setting'
        ordering = ['-id']

    def __str__(self):
        return f'SuperSetting #{self.id}'


class QrStandOrder(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='qr_stand_orders'
    )
    quantity = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=QrStandOrderStatus.choices,
        default=QrStandOrderStatus.PENDING
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_qr_stand_order'
        ordering = ['-created_at']

    def __str__(self):
        return f'QR Stand Order #{self.id} ({self.restaurant.name})'


class ShareholderWithdrawal(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='shareholder_withdrawals'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=WithdrawalStatus.choices,
        default=WithdrawalStatus.PENDING
    )
    reject_reason = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_shareholder_withdrawal'
        ordering = ['-created_at']

    def __str__(self):
        return f'Withdrawal #{self.id} - {self.amount} ({self.status})'


class BulkNotification(models.Model):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name='bulk_notifications'
    )
    message = models.TextField()
    customers = models.ManyToManyField(
        Customer, related_name='bulk_notifications', blank=True
    )
    image = models.ImageField(upload_to='notifications/', blank=True, null=True)
    type = models.CharField(
        max_length=20, choices=BulkNotificationType.choices
    )
    sent_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_bulk_notification'
        ordering = ['-created_at']

    def __str__(self):
        return f'BulkNotification #{self.id} ({self.type})'


class InAppNotification(models.Model):
    """In-app notification: one sender, one recipient (user or customer)."""
    sender = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='sent_in_app_notifications'
    )
    recipient_user = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name='received_in_app_notifications',
        null=True, blank=True
    )
    recipient_customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='received_in_app_notifications',
        null=True, blank=True
    )
    purpose = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'core_in_app_notification'
        ordering = ['-created_at']

    def __str__(self):
        return f'InAppNotification #{self.id} from {self.sender_id}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.recipient_user) == bool(self.recipient_customer):
            raise ValidationError('Exactly one of recipient_user or recipient_customer must be set.')


class HelpSupportEntry(models.Model):
    """FAQ / Help & Support content. Ordered entries shown on Help page."""
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_help_support_entry'
        ordering = ['order', 'id']

    def __str__(self):
        return self.title
