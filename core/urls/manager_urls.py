"""Manager API URL configuration. Reuses owner views for most resources (scoped by get_restaurant_ids)."""
from django.urls import path
from core.utils import auth_required
from core.permissions import manager_required, manager_unlocked
from core.views.manager.dashboard_views import manager_dashboard
from core.views.manager.attendance_views import manager_attendance_list, manager_attendance_set, manager_attendance_summary, manager_attendance_delete
from core.views.manager.notification_views import manager_notification_list, manager_notification_create
from core.views.in_app_notification_views import (
    in_app_notification_list_staff,
    in_app_notification_create,
    in_app_notification_recipients,
)
from core.views.owner.order_views import owner_order_list, owner_order_detail, owner_order_create, owner_order_update, owner_order_payment_qr, owner_order_bill
from core.views.owner.table_views import owner_table_list, owner_table_create, owner_table_update, owner_table_delete
from core.views.owner.restaurant_views import owner_restaurant_list, owner_restaurant_detail, owner_restaurant_update
from core.views.owner.qr_order_views import owner_qr_order_list, owner_qr_order_create
from core.views.owner.settings_views import owner_settings
from core.views.owner.product_views import owner_product_list, owner_product_detail, owner_product_create, owner_product_update, owner_product_upload_image, owner_product_delete
from core.views.owner.category_views import owner_category_list, owner_category_create, owner_category_update, owner_category_delete, owner_category_upload_image
from core.views.owner.unit_views import owner_unit_list, owner_unit_create, owner_unit_update, owner_unit_delete
from core.views.owner.combo_views import owner_combo_list, owner_combo_create, owner_combo_update, owner_combo_upload_image, owner_combo_delete
from core.views.owner.recipe_views import owner_recipe_list, owner_recipe_create, owner_recipe_update, owner_recipe_delete, owner_recipe_upload_image
from core.views.owner.raw_material_views import owner_raw_material_list, owner_raw_material_create, owner_raw_material_update, owner_raw_material_delete, owner_raw_material_upload_image
from core.views.owner.vendor_views import owner_vendor_list, owner_vendor_create, owner_vendor_update, owner_vendor_delete, owner_vendor_analytics
from core.views.owner.purchase_views import owner_purchase_list, owner_purchase_detail, owner_purchase_create, owner_purchase_update
from core.views.owner.staff_views import owner_available_users, owner_user_check, owner_user_create, owner_user_update, owner_staff_list_or_create, owner_staff_create, owner_staff_update, owner_staff_delete
from core.views.owner.leaderboard_views import owner_leaderboard
from core.views.owner.customer_views import owner_customer_list, owner_customer_detail
from core.views.owner.order_views import owner_customer_order_list
from core.views.owner.feedback_views import owner_feedback_list
from core.views.owner.expense_views import owner_expense_list, owner_expense_detail, owner_expense_create, owner_expense_update, owner_expense_upload_image, owner_expense_delete
from core.views.owner.paid_received_views import owner_paid_list, owner_received_list, owner_paid_create, owner_received_create
from core.views.owner.pl_views import owner_pl
from core.views.owner.analytics_views import owner_analytics
from core.views.owner.stock_log_views import owner_stock_log_list
from core.views.transaction_history_views import manager_transaction_history


def _manager_view(view_func):
    """Wrap view with auth, manager role check, and due-balance lock check."""
    return auth_required(manager_required(manager_unlocked(view_func)))


urlpatterns = [
    path('dashboard/', _manager_view(manager_dashboard)),
    path('restaurants/', _manager_view(owner_restaurant_list)),
    path('restaurants/<int:pk>/', _manager_view(owner_restaurant_detail)),
    path('restaurants/<int:pk>/update/', _manager_view(owner_restaurant_update)),
    path('qr-orders/', _manager_view(owner_qr_order_list)),
    path('qr-orders/create/', _manager_view(owner_qr_order_create)),
    path('settings/', _manager_view(owner_settings)),
    path('attendance/', _manager_view(manager_attendance_list)),
    path('attendance/summary/', _manager_view(manager_attendance_summary)),
    path('attendance/set/', _manager_view(manager_attendance_set)),
    path('attendance/<int:id>/delete/', _manager_view(manager_attendance_delete)),
    path('notifications/', _manager_view(manager_notification_list)),
    path('notifications/create/', _manager_view(manager_notification_create)),
    path('in-app-notifications/', _manager_view(in_app_notification_list_staff)),
    path('in-app-notifications/send/', _manager_view(in_app_notification_create)),
    path('in-app-notifications/recipients/', _manager_view(in_app_notification_recipients)),
    path('orders/', _manager_view(owner_order_list)),
    path('orders/create/', _manager_view(owner_order_create)),
    path('orders/<int:pk>/', _manager_view(owner_order_detail)),
    path('orders/<int:pk>/update/', _manager_view(owner_order_update)),
    path('orders/<int:pk>/payment-qr/', _manager_view(owner_order_payment_qr)),
    path('orders/<int:pk>/bill/', _manager_view(owner_order_bill)),
    path('tables/', _manager_view(owner_table_list)),
    path('tables/create/', _manager_view(owner_table_create)),
    path('tables/<int:pk>/update/', _manager_view(owner_table_update)),
    path('tables/<int:pk>/delete/', _manager_view(owner_table_delete)),
    path('products/', _manager_view(owner_product_list)),
    path('products/<int:pk>/', _manager_view(owner_product_detail)),
    path('products/create/', _manager_view(owner_product_create)),
    path('products/<int:pk>/update/', _manager_view(owner_product_update)),
    path('products/<int:pk>/upload-image/', _manager_view(owner_product_upload_image)),
    path('products/<int:pk>/delete/', _manager_view(owner_product_delete)),
    path('categories/', _manager_view(owner_category_list)),
    path('categories/create/', _manager_view(owner_category_create)),
    path('categories/<int:pk>/update/', _manager_view(owner_category_update)),
    path('categories/<int:pk>/upload-image/', _manager_view(owner_category_upload_image)),
    path('categories/<int:pk>/delete/', _manager_view(owner_category_delete)),
    path('units/', _manager_view(owner_unit_list)),
    path('units/create/', _manager_view(owner_unit_create)),
    path('units/<int:pk>/update/', _manager_view(owner_unit_update)),
    path('units/<int:pk>/delete/', _manager_view(owner_unit_delete)),
    path('combos/', _manager_view(owner_combo_list)),
    path('combos/create/', _manager_view(owner_combo_create)),
    path('combos/<int:pk>/update/', _manager_view(owner_combo_update)),
    path('combos/<int:pk>/upload-image/', _manager_view(owner_combo_upload_image)),
    path('combos/<int:pk>/delete/', _manager_view(owner_combo_delete)),
    path('recipe-mapping/', _manager_view(owner_recipe_list)),
    path('recipe-mapping/create/', _manager_view(owner_recipe_create)),
    path('recipe-mapping/<int:pk>/update/', _manager_view(owner_recipe_update)),
    path('recipe-mapping/<int:pk>/upload-image/', _manager_view(owner_recipe_upload_image)),
    path('recipe-mapping/<int:pk>/delete/', _manager_view(owner_recipe_delete)),
    path('raw-materials/', _manager_view(owner_raw_material_list)),
    path('raw-materials/create/', _manager_view(owner_raw_material_create)),
    path('raw-materials/<int:pk>/update/', _manager_view(owner_raw_material_update)),
    path('raw-materials/<int:pk>/upload-image/', _manager_view(owner_raw_material_upload_image)),
    path('raw-materials/<int:pk>/delete/', _manager_view(owner_raw_material_delete)),
    path('vendors/', _manager_view(owner_vendor_list)),
    path('vendors/create/', _manager_view(owner_vendor_create)),
    path('vendors/<int:pk>/analytics/', _manager_view(owner_vendor_analytics)),
    path('vendors/<int:pk>/update/', _manager_view(owner_vendor_update)),
    path('vendors/<int:pk>/delete/', _manager_view(owner_vendor_delete)),
    path('purchases/', _manager_view(owner_purchase_list)),
    path('purchases/<int:pk>/', _manager_view(owner_purchase_detail)),
    path('purchases/create/', _manager_view(owner_purchase_create)),
    path('purchases/<int:pk>/update/', _manager_view(owner_purchase_update)),
    path('available-users/', _manager_view(owner_available_users)),
    path('users/check/', _manager_view(owner_user_check)),
    path('users/create/', _manager_view(owner_user_create)),
    path('users/<int:user_id>/update/', _manager_view(owner_user_update)),
    path('staff/', _manager_view(owner_staff_list_or_create)),
    path('staff/create/', _manager_view(owner_staff_create)),
    path('staff/<int:pk>/update/', _manager_view(owner_staff_update)),
    path('staff/<int:pk>/delete/', _manager_view(owner_staff_delete)),
    path('leaderboard/', _manager_view(owner_leaderboard)),
    path('customers/', _manager_view(owner_customer_list)),
    path('customers/<int:pk>/orders/', _manager_view(owner_customer_order_list)),
    path('customers/<int:pk>/', _manager_view(owner_customer_detail)),
    path('feedback/', _manager_view(owner_feedback_list)),
    path('expenses/', _manager_view(owner_expense_list)),
    path('expenses/create/', _manager_view(owner_expense_create)),
    path('expenses/<int:pk>/', _manager_view(owner_expense_detail)),
    path('expenses/<int:pk>/update/', _manager_view(owner_expense_update)),
    path('expenses/<int:pk>/upload-image/', _manager_view(owner_expense_upload_image)),
    path('expenses/<int:pk>/delete/', _manager_view(owner_expense_delete)),
    path('paid/', _manager_view(owner_paid_list)),
    path('paid/create/', _manager_view(owner_paid_create)),
    path('received/', _manager_view(owner_received_list)),
    path('received/create/', _manager_view(owner_received_create)),
    path('pl/', _manager_view(owner_pl)),
    path('analytics/', _manager_view(owner_analytics)),
    path('stock-logs/', _manager_view(owner_stock_log_list)),
    path('transaction-history/', _manager_view(manager_transaction_history)),
]
