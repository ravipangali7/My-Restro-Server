"""Customer API URL configuration. Auth routes are public; others require customer_auth_required. Login is unified at /api/auth/login/."""
from django.urls import path
from core.utils import customer_auth_required
from core.views.customer.auth_views import (
    customer_register,
    customer_logout,
    customer_change_password,
    customer_request_reset,
    customer_confirm_reset,
)
from core.views.customer.dashboard_views import customer_dashboard
from core.views.customer.order_views import customer_order_list, customer_order_detail, customer_order_bill
from core.views.customer.feedback_views import customer_feedback_list
from core.views.customer.profile_views import customer_profile_get, customer_profile_update
from core.views.customer.pending_payments_views import customer_pending_payments
from core.views.transaction_history_views import customer_transaction_history

urlpatterns = [
    path('auth/register/', customer_register),
    path('auth/logout/', customer_logout),
    path('auth/change-password/', customer_change_password),
    path('auth/request-reset/', customer_request_reset),
    path('auth/confirm-reset/', customer_confirm_reset),
    path('dashboard/', customer_dashboard),
    path('orders/', customer_order_list),
    path('orders/<int:pk>/', customer_order_detail),
    path('orders/<int:pk>/bill/', customer_order_bill),
    path('feedback/', customer_feedback_list),
    path('profile/', customer_profile_get),
    path('profile/update/', customer_profile_update),
    path('pending-payments/', customer_pending_payments),
    path('transaction-history/', customer_auth_required(customer_transaction_history)),
]
