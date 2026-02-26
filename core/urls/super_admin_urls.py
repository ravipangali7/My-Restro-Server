"""Super Admin API URL configuration. All views require auth + is_superuser (403 for non-super_admin)."""
from django.urls import path
from core.utils import super_admin_required
from core.views.super_admin.dashboard_views import super_admin_dashboard
from core.views.super_admin.restaurant_views import (
    super_admin_restaurant_list,
    super_admin_restaurant_detail,
    super_admin_restaurant_create,
    super_admin_restaurant_update,
    super_admin_restaurant_delete,
    super_admin_restaurant_check_slug,
)
from core.views.super_admin.kyc_views import super_admin_kyc_list, super_admin_kyc_approve_reject
from core.views.super_admin.owner_views import (
    super_admin_owner_list,
    super_admin_owner_detail,
    super_admin_owner_create,
    super_admin_owner_update,
    super_admin_owner_delete,
)
from core.views.super_admin.finance_views import super_admin_finance
from core.views.super_admin.transaction_views import super_admin_transaction_list
from core.views.super_admin.customer_views import super_admin_customer_list
from core.views.super_admin.notification_views import super_admin_notification_list
from core.views.super_admin.dues_views import super_admin_dues_list
from core.views.transaction_history_views import super_admin_transaction_history
from core.views.super_admin.shareholder_views import (
    super_admin_shareholder_list,
    super_admin_shareholder_detail,
    super_admin_shareholder_create,
    super_admin_shareholder_update,
)
from core.views.super_admin.reports_views import super_admin_reports, super_admin_reports_restaurants, super_admin_reports_export
from core.views.super_admin.share_distribution_views import (
    super_admin_share_distribution_list,
    super_admin_share_distribution_preview,
    super_admin_share_distribution_run,
)
from core.views.super_admin.withdrawal_views import (
    super_admin_withdrawal_list,
    super_admin_withdrawal_detail,
    super_admin_withdrawal_create,
    super_admin_withdrawal_update,
    super_admin_withdrawal_delete,
    super_admin_withdrawal_approve_reject,
    super_admin_withdrawal_eligible_users,
)
from core.views.super_admin.qr_order_views import (
    super_admin_qr_order_list,
    super_admin_qr_order_create,
    super_admin_qr_order_detail,
    super_admin_qr_order_update,
    super_admin_qr_order_delete,
)
from core.views.super_admin.settings_views import super_admin_settings_get, super_admin_settings_patch
from core.views.super_admin.profile_views import (
    super_admin_profile_list,
    super_admin_profile_detail,
    super_admin_profile_update,
)
from core.views.super_admin.auth_views import (
    super_admin_request_password_reset,
    super_admin_confirm_password_reset,
)
from core.views.help_support_views import (
    super_admin_help_support_list,
    super_admin_help_support_update,
    super_admin_help_support_create,
)
from core.views.in_app_notification_views import (
    in_app_notification_list_staff,
    in_app_notification_create,
    in_app_notification_recipients,
)

urlpatterns = [
    path('dashboard/', super_admin_required(super_admin_dashboard)),
    path('restaurants/check-slug/', super_admin_required(super_admin_restaurant_check_slug)),
    path('restaurants/', super_admin_required(super_admin_restaurant_list)),
    path('restaurants/<int:pk>/', super_admin_required(super_admin_restaurant_detail)),
    path('restaurants/create/', super_admin_required(super_admin_restaurant_create)),
    path('restaurants/<int:pk>/update/', super_admin_required(super_admin_restaurant_update)),
    path('restaurants/<int:pk>/delete/', super_admin_required(super_admin_restaurant_delete)),
    path('kyc/', super_admin_required(super_admin_kyc_list)),
    path('kyc/<int:pk>/approve-reject/', super_admin_required(super_admin_kyc_approve_reject)),
    path('owners/', super_admin_required(super_admin_owner_list)),
    path('owners/create/', super_admin_required(super_admin_owner_create)),
    path('owners/<int:pk>/', super_admin_required(super_admin_owner_detail)),
    path('owners/<int:pk>/update/', super_admin_required(super_admin_owner_update)),
    path('owners/<int:pk>/delete/', super_admin_required(super_admin_owner_delete)),
    path('finance/', super_admin_required(super_admin_finance)),
    path('customers/', super_admin_required(super_admin_customer_list)),
    path('notifications/', super_admin_required(super_admin_notification_list)),
    path('in-app-notifications/', super_admin_required(in_app_notification_list_staff)),
    path('in-app-notifications/send/', super_admin_required(in_app_notification_create)),
    path('in-app-notifications/recipients/', super_admin_required(in_app_notification_recipients)),
    path('dues/', super_admin_required(super_admin_dues_list)),
    path('transactions/', super_admin_required(super_admin_transaction_list)),
    path('transaction-history/', super_admin_required(super_admin_transaction_history)),
    path('shareholders/', super_admin_required(super_admin_shareholder_list)),
    path('shareholders/<int:pk>/', super_admin_required(super_admin_shareholder_detail)),
    path('shareholders/create/', super_admin_required(super_admin_shareholder_create)),
    path('shareholders/<int:pk>/update/', super_admin_required(super_admin_shareholder_update)),
    path('reports/', super_admin_required(super_admin_reports)),
    path('reports/restaurants/', super_admin_required(super_admin_reports_restaurants)),
    path('reports/export/', super_admin_required(super_admin_reports_export)),
    path('share-distribution/', super_admin_required(super_admin_share_distribution_list)),
    path('share-distribution/preview/', super_admin_required(super_admin_share_distribution_preview)),
    path('share-distribution/run/', super_admin_required(super_admin_share_distribution_run)),
    path('withdrawals/', super_admin_required(super_admin_withdrawal_list)),
    path('withdrawals/eligible-users/', super_admin_required(super_admin_withdrawal_eligible_users)),
    path('withdrawals/create/', super_admin_required(super_admin_withdrawal_create)),
    path('withdrawals/<int:pk>/', super_admin_required(super_admin_withdrawal_detail)),
    path('withdrawals/<int:pk>/update/', super_admin_required(super_admin_withdrawal_update)),
    path('withdrawals/<int:pk>/delete/', super_admin_required(super_admin_withdrawal_delete)),
    path('withdrawals/<int:pk>/approve-reject/', super_admin_required(super_admin_withdrawal_approve_reject)),
    path('qr-orders/', super_admin_required(super_admin_qr_order_list)),
    path('qr-orders/create/', super_admin_required(super_admin_qr_order_create)),
    path('qr-orders/<int:pk>/', super_admin_required(super_admin_qr_order_detail)),
    path('qr-orders/<int:pk>/update/', super_admin_required(super_admin_qr_order_update)),
    path('qr-orders/<int:pk>/delete/', super_admin_required(super_admin_qr_order_delete)),
    path('settings/', super_admin_required(super_admin_settings_get)),
    path('settings/patch/', super_admin_required(super_admin_settings_patch)),
    path('profiles/', super_admin_required(super_admin_profile_list)),
    path('profiles/<int:pk>/', super_admin_required(super_admin_profile_detail)),
    path('profiles/<int:pk>/update/', super_admin_required(super_admin_profile_update)),
    path('auth/request-password-reset/', super_admin_required(super_admin_request_password_reset)),
    path('auth/confirm-password-reset/', super_admin_required(super_admin_confirm_password_reset)),
    path('help-support/', super_admin_required(super_admin_help_support_list)),
    path('help-support/create/', super_admin_required(super_admin_help_support_create)),
    path('help-support/<int:pk>/update/', super_admin_required(super_admin_help_support_update)),
]
