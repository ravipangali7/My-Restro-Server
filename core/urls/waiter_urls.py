"""Waiter API URL configuration. All views wrapped with auth + waiter_required + waiter_unlocked."""
from django.urls import path
from core.utils import auth_required
from core.permissions import waiter_required, waiter_unlocked
from core.views.waiter.dashboard_views import waiter_dashboard
from core.views.waiter.order_views import waiter_order_list, waiter_order_detail, waiter_order_update, waiter_order_create, waiter_order_new_count, waiter_order_payment_qr
from core.views.waiter.bill_views import waiter_order_bill, waiter_order_qt_receipt
from core.views.waiter.table_views import waiter_table_list
from core.views.waiter.call_views import waiter_call_list, waiter_call_pending_count, waiter_call_update
from core.views.waiter.feedback_views import waiter_feedback_list
from core.views.waiter.attendance_views import waiter_attendance_list
from core.views.waiter.profile_views import waiter_profile, waiter_profile_update
from core.views.transaction_history_views import waiter_transaction_history
from core.views.waiter.qr_order_views import waiter_qr_order_list, waiter_qr_order_create
from core.views.waiter.menu_views import waiter_product_list, waiter_category_list
from core.views.owner.restaurant_views import owner_restaurant_list, owner_restaurant_detail
from core.views.in_app_notification_views import (
    in_app_notification_list_staff,
    in_app_notification_create,
    in_app_notification_recipients,
)


def _waiter_view(view_func):
    """Wrap view with auth, waiter role check, and due-balance lock check."""
    return auth_required(waiter_required(waiter_unlocked(view_func)))


urlpatterns = [
    path('restaurants/', _waiter_view(owner_restaurant_list)),
    path('restaurants/<int:pk>/', _waiter_view(owner_restaurant_detail)),
    path('dashboard/', _waiter_view(waiter_dashboard)),
    path('calls/', _waiter_view(waiter_call_list)),
    path('calls/pending-count/', _waiter_view(waiter_call_pending_count)),
    path('calls/<int:pk>/', _waiter_view(waiter_call_update)),
    path('orders/', _waiter_view(waiter_order_list)),
    path('orders/new-count/', _waiter_view(waiter_order_new_count)),
    path('orders/create/', _waiter_view(waiter_order_create)),
    path('orders/<int:pk>/', _waiter_view(waiter_order_detail)),
    path('orders/<int:pk>/update/', _waiter_view(waiter_order_update)),
    path('orders/<int:pk>/payment-qr/', _waiter_view(waiter_order_payment_qr)),
    path('orders/<int:pk>/bill/', _waiter_view(waiter_order_bill)),
    path('orders/<int:pk>/qt-receipt/', _waiter_view(waiter_order_qt_receipt)),
    path('tables/', _waiter_view(waiter_table_list)),
    path('products/', _waiter_view(waiter_product_list)),
    path('categories/', _waiter_view(waiter_category_list)),
    path('feedback/', _waiter_view(waiter_feedback_list)),
    path('attendance/', _waiter_view(waiter_attendance_list)),
    path('profile/', _waiter_view(waiter_profile)),
    path('profile/update/', _waiter_view(waiter_profile_update)),
    path('transaction-history/', _waiter_view(waiter_transaction_history)),
    path('qr-orders/', _waiter_view(waiter_qr_order_list)),
    path('qr-orders/create/', _waiter_view(waiter_qr_order_create)),
    path('in-app-notifications/', _waiter_view(in_app_notification_list_staff)),
    path('in-app-notifications/send/', _waiter_view(in_app_notification_create)),
    path('in-app-notifications/recipients/', _waiter_view(in_app_notification_recipients)),
]
