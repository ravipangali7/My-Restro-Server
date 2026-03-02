"""Waiter API URL configuration. All views wrapped with auth + waiter_required + waiter_unlocked + permission."""
from django.urls import path
from core.utils import auth_required
from core.permissions import waiter_required, waiter_unlocked
from core.rbac import require_permission
from core.views.waiter.dashboard_views import waiter_dashboard
from core.views.waiter.order_views import waiter_order_list, waiter_order_detail, waiter_order_update, waiter_order_create, waiter_order_new_count, waiter_order_payment_qr
from core.views.waiter.bill_views import waiter_order_bill, waiter_order_qt_receipt
from core.views.waiter.table_views import waiter_table_list
from core.views.waiter.feedback_views import waiter_feedback_list
from core.views.waiter.attendance_views import waiter_attendance_list
from core.views.waiter.profile_views import waiter_profile, waiter_profile_update
from core.views.transaction_history_views import waiter_transaction_history
from core.views.waiter.qr_order_views import waiter_qr_order_list, waiter_qr_order_create
from core.views.waiter.menu_views import waiter_product_list, waiter_category_list
from core.views.owner.restaurant_views import owner_restaurant_list, owner_restaurant_detail


def _waiter_view(view_func):
    """Wrap view with auth, waiter role check, and due-balance lock check."""
    return auth_required(waiter_required(waiter_unlocked(view_func)))


def _waiter_view_perm(permission_code):
    """Wrap view with auth, waiter role, unlock check, and permission check."""
    def wrapper(view_func):
        return auth_required(waiter_required(waiter_unlocked(require_permission(permission_code)(view_func))))
    return wrapper


urlpatterns = [
    path('restaurants/', _waiter_view_perm('manage_orders')(owner_restaurant_list)),
    path('restaurants/<int:pk>/', _waiter_view_perm('manage_orders')(owner_restaurant_detail)),
    path('dashboard/', _waiter_view_perm('view_my_performance')(waiter_dashboard)),
    path('orders/', _waiter_view_perm('manage_orders')(waiter_order_list)),
    path('orders/new-count/', _waiter_view_perm('manage_orders')(waiter_order_new_count)),
    path('orders/create/', _waiter_view_perm('manage_orders')(waiter_order_create)),
    path('orders/<int:pk>/', _waiter_view_perm('manage_orders')(waiter_order_detail)),
    path('orders/<int:pk>/update/', _waiter_view_perm('manage_orders')(waiter_order_update)),
    path('orders/<int:pk>/payment-qr/', _waiter_view_perm('manage_orders')(waiter_order_payment_qr)),
    path('orders/<int:pk>/bill/', _waiter_view_perm('manage_orders')(waiter_order_bill)),
    path('orders/<int:pk>/qt-receipt/', _waiter_view_perm('manage_orders')(waiter_order_qt_receipt)),
    path('tables/', _waiter_view_perm('manage_orders')(waiter_table_list)),
    path('products/', _waiter_view_perm('manage_orders')(waiter_product_list)),
    path('categories/', _waiter_view_perm('manage_orders')(waiter_category_list)),
    path('feedback/', _waiter_view_perm('manage_feedback')(waiter_feedback_list)),
    path('attendance/', _waiter_view_perm('manage_attendance')(waiter_attendance_list)),
    path('profile/', _waiter_view_perm('view_salary')(waiter_profile)),
    path('profile/update/', _waiter_view_perm('view_salary')(waiter_profile_update)),
    path('transaction-history/', _waiter_view_perm('manage_orders')(waiter_transaction_history)),
    path('qr-orders/', _waiter_view_perm('manage_orders')(waiter_qr_order_list)),
    path('qr-orders/create/', _waiter_view_perm('manage_orders')(waiter_qr_order_create)),
]
