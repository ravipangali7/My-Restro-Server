"""Owner API URL configuration. All views use auth_required + owner_required; non-payment views also use owner_unlocked."""
from django.urls import path
from core.utils import auth_required
from core.permissions import owner_required, owner_or_superuser_required, owner_unlocked
from core.views.owner.dashboard_views import owner_dashboard
from core.views.owner.payment_views import (
    owner_subscription_preview,
    owner_qr_stand_preview,
    owner_pay_subscription,
    owner_pay_qr_stand,
    owner_pay_due,
)
from core.views.owner.restaurant_views import (
    owner_restaurant_list,
    owner_restaurant_detail,
    owner_restaurant_create,
    owner_restaurant_update,
    owner_restaurant_delete,
    owner_restaurant_check_slug,
)
from core.views.owner.order_views import (
    owner_order_list,
    owner_order_detail,
    owner_order_create,
    owner_order_update,
    owner_order_payment_qr,
    owner_order_bill,
    owner_customer_order_list,
)
from core.views.owner.product_views import (
    owner_product_list,
    owner_product_detail,
    owner_product_create,
    owner_product_update,
    owner_product_upload_image,
    owner_product_delete,
)
from core.views.owner.category_views import (
    owner_category_list,
    owner_category_create,
    owner_category_update,
    owner_category_delete,
    owner_category_upload_image,
)
from core.views.owner.unit_views import (
    owner_unit_list,
    owner_unit_create,
    owner_unit_update,
    owner_unit_delete,
)
from core.views.owner.combo_views import (
    owner_combo_list,
    owner_combo_create,
    owner_combo_update,
    owner_combo_upload_image,
    owner_combo_delete,
)
from core.views.owner.raw_material_views import (
    owner_raw_material_list,
    owner_raw_material_create,
    owner_raw_material_update,
    owner_raw_material_delete,
    owner_raw_material_upload_image,
)
from core.views.owner.vendor_views import (
    owner_vendor_list,
    owner_vendor_create,
    owner_vendor_update,
    owner_vendor_delete,
    owner_vendor_upload_image,
    owner_vendor_analytics,
)
from core.views.owner.purchase_views import (
    owner_purchase_list,
    owner_purchase_detail,
    owner_purchase_create,
    owner_purchase_update,
)
from core.views.owner.staff_views import (
    owner_available_users,
    owner_user_check,
    owner_user_create,
    owner_user_update,
    owner_staff_list_or_create,
    owner_staff_create,
    owner_staff_update,
    owner_staff_delete,
)
from core.views.owner.recipe_views import (
    owner_recipe_list,
    owner_recipe_create,
    owner_recipe_update,
    owner_recipe_delete,
    owner_recipe_upload_image,
)
from core.views.owner.customer_views import owner_customer_list, owner_customer_detail, owner_customer_create
from core.views.owner.leaderboard_views import owner_leaderboard
from core.views.owner.analytics_views import owner_analytics
from core.views.owner.pl_views import owner_pl
from core.views.owner.table_views import (
    owner_table_list,
    owner_table_create,
    owner_table_update,
    owner_table_delete,
)
from core.views.owner.feedback_views import owner_feedback_list
from core.views.owner.stock_log_views import owner_stock_log_list
from core.views.owner.attendance_views import owner_attendance_summary
from core.views.owner.reports_views import owner_reports
from core.views.owner.qr_order_views import owner_qr_order_list, owner_qr_order_create
from core.views.owner.settings_views import owner_settings
from core.views.transaction_history_views import owner_transaction_history


def _owner_access(view_func):
    """auth_required + owner_or_superuser_required + owner_unlocked (any active owner can use)."""
    return auth_required(owner_or_superuser_required(owner_unlocked(view_func)))


def _owner_access_when_locked(view_func):
    """Like _owner_access but without owner_unlocked, so dashboard/restaurants load when due balance is over threshold (owner can then open Payments)."""
    return auth_required(owner_or_superuser_required(view_func))


def _owner_dashboard_access(view_func):
    """auth_required + owner_required (KYC approved) + owner_unlocked; for dashboard only."""
    return auth_required(owner_required(owner_unlocked(view_func)))


def _owner_payment_access(view_func):
    """auth_required + owner_required (KYC approved) only (owner can pay when locked)."""
    return auth_required(owner_required(view_func))


urlpatterns = [
    path('dashboard/', _owner_access_when_locked(owner_dashboard)),
    path('payments/subscription/preview/', _owner_payment_access(owner_subscription_preview)),
    path('payments/subscription/', _owner_payment_access(owner_pay_subscription)),
    path('payments/qr-stand/preview/', _owner_payment_access(owner_qr_stand_preview)),
    path('payments/qr-stand/', _owner_payment_access(owner_pay_qr_stand)),
    path('payments/due/', _owner_payment_access(owner_pay_due)),
    path('restaurants/check-slug/', _owner_access_when_locked(owner_restaurant_check_slug)),
    path('restaurants/', _owner_access_when_locked(owner_restaurant_list)),
    path('restaurants/<int:pk>/', _owner_access_when_locked(owner_restaurant_detail)),
    path('restaurants/create/', _owner_access_when_locked(owner_restaurant_create)),
    path('restaurants/<int:pk>/update/', _owner_access_when_locked(owner_restaurant_update)),
    path('restaurants/<int:pk>/delete/', _owner_access_when_locked(owner_restaurant_delete)),
    path('orders/', _owner_access_when_locked(owner_order_list)),
    path('orders/<int:pk>/', _owner_access_when_locked(owner_order_detail)),
    path('orders/create/', _owner_access_when_locked(owner_order_create)),
    path('orders/<int:pk>/update/', _owner_access_when_locked(owner_order_update)),
    path('orders/<int:pk>/payment-qr/', _owner_access_when_locked(owner_order_payment_qr)),
    path('orders/<int:pk>/bill/', _owner_access_when_locked(owner_order_bill)),
    path('qr-orders/', _owner_access_when_locked(owner_qr_order_list)),
    path('qr-orders/create/', _owner_access_when_locked(owner_qr_order_create)),
    path('settings/', _owner_access_when_locked(owner_settings)),
    path('products/', _owner_access_when_locked(owner_product_list)),
    path('products/<int:pk>/', _owner_access_when_locked(owner_product_detail)),
    path('products/create/', _owner_access_when_locked(owner_product_create)),
    path('products/<int:pk>/update/', _owner_access_when_locked(owner_product_update)),
    path('products/<int:pk>/upload-image/', _owner_access_when_locked(owner_product_upload_image)),
    path('products/<int:pk>/delete/', _owner_access_when_locked(owner_product_delete)),
    path('categories/', _owner_access_when_locked(owner_category_list)),
    path('categories/create/', _owner_access_when_locked(owner_category_create)),
    path('categories/<int:pk>/update/', _owner_access_when_locked(owner_category_update)),
    path('categories/<int:pk>/upload-image/', _owner_access_when_locked(owner_category_upload_image)),
    path('categories/<int:pk>/delete/', _owner_access_when_locked(owner_category_delete)),
    path('units/', _owner_access_when_locked(owner_unit_list)),
    path('units/create/', _owner_access_when_locked(owner_unit_create)),
    path('units/<int:pk>/update/', _owner_access_when_locked(owner_unit_update)),
    path('units/<int:pk>/delete/', _owner_access_when_locked(owner_unit_delete)),
    path('combos/', _owner_access_when_locked(owner_combo_list)),
    path('combos/create/', _owner_access_when_locked(owner_combo_create)),
    path('combos/<int:pk>/update/', _owner_access_when_locked(owner_combo_update)),
    path('combos/<int:pk>/upload-image/', _owner_access_when_locked(owner_combo_upload_image)),
    path('combos/<int:pk>/delete/', _owner_access_when_locked(owner_combo_delete)),
    path('raw-materials/', _owner_access_when_locked(owner_raw_material_list)),
    path('raw-materials/create/', _owner_access_when_locked(owner_raw_material_create)),
    path('raw-materials/<int:pk>/update/', _owner_access_when_locked(owner_raw_material_update)),
    path('raw-materials/<int:pk>/upload-image/', _owner_access_when_locked(owner_raw_material_upload_image)),
    path('raw-materials/<int:pk>/delete/', _owner_access_when_locked(owner_raw_material_delete)),
    path('vendors/', _owner_access_when_locked(owner_vendor_list)),
    path('vendors/create/', _owner_access_when_locked(owner_vendor_create)),
    path('vendors/<int:pk>/analytics/', _owner_access_when_locked(owner_vendor_analytics)),
    path('vendors/<int:pk>/update/', _owner_access_when_locked(owner_vendor_update)),
    path('vendors/<int:pk>/upload-image/', _owner_access_when_locked(owner_vendor_upload_image)),
    path('vendors/<int:pk>/delete/', _owner_access_when_locked(owner_vendor_delete)),
    path('purchases/', _owner_access_when_locked(owner_purchase_list)),
    path('purchases/<int:pk>/', _owner_access_when_locked(owner_purchase_detail)),
    path('purchases/create/', _owner_access_when_locked(owner_purchase_create)),
    path('purchases/<int:pk>/update/', _owner_access_when_locked(owner_purchase_update)),
    path('available-users/', _owner_access_when_locked(owner_available_users)),
    path('users/check/', _owner_access_when_locked(owner_user_check)),
    path('users/create/', _owner_access_when_locked(owner_user_create)),
    path('users/<int:user_id>/update/', _owner_access_when_locked(owner_user_update)),
    path('staff/', _owner_access_when_locked(owner_staff_list_or_create)),
    path('staff/create/', _owner_access_when_locked(owner_staff_create)),
    path('staff/<int:pk>/update/', _owner_access_when_locked(owner_staff_update)),
    path('staff/<int:pk>/delete/', _owner_access_when_locked(owner_staff_delete)),
    path('attendance/summary/', _owner_access_when_locked(owner_attendance_summary)),
    path('recipe-mapping/', _owner_access_when_locked(owner_recipe_list)),
    path('recipe-mapping/create/', _owner_access_when_locked(owner_recipe_create)),
    path('recipe-mapping/<int:pk>/update/', _owner_access_when_locked(owner_recipe_update)),
    path('recipe-mapping/<int:pk>/upload-image/', _owner_access_when_locked(owner_recipe_upload_image)),
    path('recipe-mapping/<int:pk>/delete/', _owner_access_when_locked(owner_recipe_delete)),
    path('customers/', _owner_access_when_locked(owner_customer_list)),
    path('customers/create/', _owner_access_when_locked(owner_customer_create)),
    path('customers/<int:pk>/orders/', _owner_access_when_locked(owner_customer_order_list)),
    path('customers/<int:pk>/', _owner_access_when_locked(owner_customer_detail)),
    path('leaderboard/', _owner_access_when_locked(owner_leaderboard)),
    path('reports/', _owner_access_when_locked(owner_reports)),
    path('analytics/', _owner_access_when_locked(owner_analytics)),
    path('pl/', _owner_access_when_locked(owner_pl)),
    path('tables/', _owner_access_when_locked(owner_table_list)),
    path('tables/create/', _owner_access_when_locked(owner_table_create)),
    path('tables/<int:pk>/update/', _owner_access_when_locked(owner_table_update)),
    path('tables/<int:pk>/delete/', _owner_access_when_locked(owner_table_delete)),
    path('feedback/', _owner_access_when_locked(owner_feedback_list)),
    path('stock-logs/', _owner_access_when_locked(owner_stock_log_list)),
    path('transaction-history/', _owner_access_when_locked(owner_transaction_history)),
]
