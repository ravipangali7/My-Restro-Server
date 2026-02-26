from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from . import services
from .models import (
    User,
    Customer,
    CustomerToken,
    CustomerRestaurant,
    Restaurant,
    Vendor,
    Unit,
    Category,
    Product,
    ProductVariant,
    ProductRawMaterial,
    ComboSet,
    RawMaterial,
    Table,
    Staff,
    Order,
    OrderItem,
    Rider,
    Delivery,
    Feedback,
    Purchase,
    PurchaseItem,
    Expenses,
    PaidRecord,
    ReceivedRecord,
    Transaction,
    StockLog,
    Attendance,
    SuperSetting,
    QrStandOrder,
    ShareholderWithdrawal,
    BulkNotification,
)


# --- Inlines ---

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ['product', 'product_variant', 'combo_set']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    autocomplete_fields = ['unit']


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    autocomplete_fields = ['raw_material']


# --- User (replace default auth User admin) ---


class CustomUserCreationForm(UserCreationForm):
    """Add form must declare custom fields so they render and save."""
    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + (
            'name', 'phone', 'country_code', 'is_owner', 'is_restaurant_staff',
        )


class CustomUserChangeForm(UserChangeForm):
    """Edit form including all custom User model fields."""
    class Meta:
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    list_display = (
        'username', 'name', 'phone', 'is_owner', 'is_restaurant_staff',
        'kyc_status', 'is_active', 'created_at'
    )
    list_filter = ('is_owner', 'is_restaurant_staff', 'kyc_status', 'is_active')
    search_fields = ('name', 'phone', 'username', 'email')
    ordering = ('-date_joined',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('None', {
            'fields': (
                'name', 'phone', 'country_code', 'image',
                'is_owner', 'is_restaurant_staff', 'kyc_status', 'reject_reason',
                'kyc_document', 'is_shareholder', 'share_percentage',
                'balance', 'due_balance', 'fcm_token',
                'created_at', 'updated_at',
            )
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('None', {
            'fields': (
                'name', 'phone', 'country_code', 'is_owner', 'is_restaurant_staff',
            )
        }),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'user', 'created_at')
    search_fields = ('name', 'phone')
    autocomplete_fields = ('user',)
    exclude = ('password',)


@admin.register(CustomerToken)
class CustomerTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'key_preview', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('customer__name', 'customer__phone')
    readonly_fields = ('created_at',)
    def key_preview(self, obj):
        return f'{obj.key[:12]}...' if obj.key and len(obj.key) > 12 else (obj.key or '')
    key_preview.short_description = 'Key'


@admin.register(CustomerRestaurant)
class CustomerRestaurantAdmin(admin.ModelAdmin):
    list_display = ('customer', 'restaurant', 'to_pay', 'to_receive', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('customer__name', 'customer__phone')
    autocomplete_fields = ('customer', 'restaurant')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'user', 'is_open', 'balance', 'due_balance', 'created_at')
    list_filter = ('is_open',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'to_pay', 'to_receive', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name',)
    autocomplete_fields = ('restaurant',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'restaurant', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name', 'symbol')
    autocomplete_fields = ('restaurant',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name',)
    autocomplete_fields = ('restaurant',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'dish_type', 'is_active', 'restaurant', 'created_at')
    list_filter = ('category', 'is_active', 'dish_type', 'restaurant')
    search_fields = ('name',)
    autocomplete_fields = ('restaurant', 'category')
    inlines = (ProductVariantInline,)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'unit', 'price', 'discount_type', 'discount', 'created_at')
    list_filter = ('product__restaurant', 'discount_type')
    search_fields = ('product__name',)
    autocomplete_fields = ('product', 'unit')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProductRawMaterial)
class ProductRawMaterialAdmin(admin.ModelAdmin):
    list_display = ('product', 'product_variant', 'raw_material', 'raw_material_quantity', 'restaurant', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('product__name', 'raw_material__name')
    autocomplete_fields = ('restaurant', 'product', 'product_variant', 'raw_material')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ComboSet)
class ComboSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'price', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name',)
    autocomplete_fields = ('restaurant',)
    filter_horizontal = ('products',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'vendor', 'stock', 'price', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name',)
    autocomplete_fields = ('restaurant', 'vendor', 'unit')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'floor', 'capacity', 'created_at')
    list_filter = ('restaurant', 'floor')
    search_fields = ('name',)
    autocomplete_fields = ('restaurant',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('user', 'restaurant', 'is_manager', 'is_waiter', 'to_pay', 'to_receive', 'created_at')
    list_filter = ('restaurant', 'is_manager', 'is_waiter')
    search_fields = ('user__username', 'user__name', 'designation')
    autocomplete_fields = ('restaurant', 'user')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'restaurant', 'table', 'order_type', 'status', 'payment_status', 'total', 'created_at')
    list_filter = ('restaurant', 'status', 'payment_status', 'order_type')
    search_fields = ('id', 'customer__name', 'customer__phone')
    autocomplete_fields = ('customer', 'restaurant', 'table', 'waiter')
    inlines = (OrderItemInline,)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'source', 'is_available', 'last_updated')
    list_filter = ('source', 'is_available')
    search_fields = ('name', 'phone')


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'order', 'rider', 'delivery_status', 'distance_km', 'eta_minutes', 'created_at')
    list_filter = ('delivery_status',)
    raw_id_fields = ('order', 'rider')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'product', 'product_variant', 'combo_set', 'price', 'quantity', 'total', 'created_at')
    list_filter = ('order__restaurant',)
    search_fields = ('order__id',)
    autocomplete_fields = ('order', 'product', 'product_variant', 'combo_set')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'customer', 'order', 'staff', 'rating', 'created_at')
    list_filter = ('restaurant', 'rating')
    search_fields = ('review',)
    autocomplete_fields = ('restaurant', 'customer', 'order', 'staff')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'subtotal', 'total', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('id',)
    autocomplete_fields = ('restaurant',)
    inlines = (PurchaseItemInline,)
    readonly_fields = ('created_at', 'updated_at')
    actions = ['create_paid_record']

    @admin.action(description='Create paid record')
    def create_paid_record(self, request, queryset):
        created = 0
        for purchase in queryset:
            if purchase.paid_records.exists():
                continue
            vendor = None
            first_item = purchase.items.select_related('raw_material').first()
            if first_item and first_item.raw_material_id:
                vendor = first_item.raw_material.vendor
            PaidRecord.objects.create(
                restaurant=purchase.restaurant,
                name=f'Purchase #{purchase.id}',
                amount=purchase.total,
                purchase=purchase,
                vendor=vendor,
            )
            created += 1
        self.message_user(request, f'Created {created} paid record(s).', messages.SUCCESS)


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'raw_material', 'purchase', 'price', 'quantity', 'total', 'created_at')
    list_filter = ('purchase__restaurant',)
    search_fields = ('raw_material__name',)
    autocomplete_fields = ('raw_material', 'purchase')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Expenses)
class ExpensesAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'vendor', 'amount', 'created_at')
    list_filter = ('restaurant',)
    search_fields = ('name', 'description')
    autocomplete_fields = ('restaurant', 'vendor')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['create_paid_record']

    @admin.action(description='Create paid record')
    def create_paid_record(self, request, queryset):
        created = 0
        for expense in queryset:
            if expense.paid_records.exists():
                continue
            PaidRecord.objects.create(
                restaurant=expense.restaurant,
                name=expense.name,
                amount=expense.amount,
                expenses=expense,
                vendor=expense.vendor,
            )
            created += 1
        self.message_user(request, f'Created {created} paid record(s).', messages.SUCCESS)


@admin.register(PaidRecord)
class PaidRecordAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'amount', 'payment_method', 'vendor', 'staff', 'created_at')
    list_filter = ('restaurant', 'payment_method')
    search_fields = ('name', 'remarks')
    autocomplete_fields = ('restaurant', 'vendor', 'purchase', 'expenses', 'staff')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ReceivedRecord)
class ReceivedRecordAdmin(admin.ModelAdmin):
    list_display = ('name', 'restaurant', 'amount', 'payment_method', 'customer', 'order', 'created_at')
    list_filter = ('restaurant', 'payment_method')
    search_fields = ('name', 'remarks')
    autocomplete_fields = ('restaurant', 'customer', 'order')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'amount', 'transaction_type', 'category', 'payment_status', 'created_at')
    list_filter = ('restaurant', 'transaction_type', 'category', 'payment_status')
    search_fields = ('remarks', 'utr', 'payer_name')
    autocomplete_fields = ('restaurant', 'paid_record', 'received_record')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockLog)
class StockLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'raw_material', 'type', 'quantity', 'created_at')
    list_filter = ('restaurant', 'type')
    search_fields = ('raw_material__name',)
    autocomplete_fields = ('restaurant', 'raw_material', 'purchase', 'purchase_item', 'order', 'order_item')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('restaurant', 'date', 'staff', 'status', 'created_at')
    list_filter = ('restaurant', 'date', 'status')
    search_fields = ('staff__user__username',)
    autocomplete_fields = ('restaurant', 'staff')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SuperSetting)
class SuperSettingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'per_qr_stand_price', 'subscription_fee_per_month', 'per_transaction_fee',
        'due_threshold', 'balance', 'created_at'
    )
    readonly_fields = ('created_at', 'updated_at')
    actions = ['run_share_distribution']

    @admin.action(description='Run share distribution')
    def run_share_distribution(self, request, queryset):
        services.apply_share_distribution()
        self.message_user(request, 'Share distribution applied.', messages.SUCCESS)


@admin.register(QrStandOrder)
class QrStandOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'quantity', 'total', 'status', 'payment_status', 'created_at')
    list_filter = ('restaurant', 'status', 'payment_status')
    autocomplete_fields = ('restaurant',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ShareholderWithdrawal)
class ShareholderWithdrawalAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'user__name')
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BulkNotification)
class BulkNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'restaurant', 'type', 'sent_count', 'total_count', 'created_at')
    list_filter = ('restaurant', 'type')
    search_fields = ('message',)
    autocomplete_fields = ('restaurant',)
    filter_horizontal = ('customers',)
    readonly_fields = ('created_at', 'updated_at')
