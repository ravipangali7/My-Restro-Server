from django.urls import path
from . import auth_views
from . import views

urlpatterns = [
    path('auth/login/', auth_views.login),
    path('auth/me/', auth_views.me),
    path('auth/logout/', auth_views.logout),
    # Owner (scoped dashboard and lists)
    path('owner/dashboard-stats/', views.owner_dashboard_stats),
    path('owner/staff/', views.owner_staff_list),
    path('owner/staff/stats/', views.owner_staff_stats),
    path('owner/customers/', views.owner_customers_list),
    path('owner/customers/stats/', views.owner_customers_stats),
    path('owner/vendors/', views.owner_vendors_list),
    path('owner/vendors/stats/', views.owner_vendors_stats),
    path('owner/payroll/', views.owner_payroll_list),
    path('owner/reports/staff/', views.owner_report_staff),
    path('owner/reports/finance/', views.owner_report_finance),
    path('owner/reports/credits/', views.owner_report_credits),
    path('owner/reports/customers/', views.owner_report_customers),
    path('owner/reports/products/', views.owner_report_products),
    path('owner/reports/inventory/', views.owner_report_inventory),
    path('owner/reports/pl/', views.owner_report_pl),
    # Super admin: Owners
    path('owners/stats/', views.owner_stats),
    path('owners/analytics/', views.owner_analytics),
    path('owners/search/', views.owner_search),
    path('owners/', views.owner_list),
    path('owners/<int:pk>/', views.owner_detail),
    # Restaurants (super admin)
    path('restaurants/stats/', views.restaurant_stats),
    path('restaurants/analytics/', views.restaurant_analytics),
    path('restaurants/', views.restaurant_list),
    path('restaurants/<int:pk>/pay-due/', views.restaurant_pay_due),
    path('restaurants/<int:pk>/', views.restaurant_detail),
    # Due (super admin)
    path('due/stats/', views.due_stats),
    # KYC (super admin)
    path('kyc/stats/', views.kyc_stats),
    path('kyc/', views.kyc_list),
    # Shareholders (super admin)
    path('shareholders/stats/', views.shareholder_stats),
    path('shareholders/analytics/', views.shareholder_analytics),
    path('shareholders/search/', views.shareholder_search),
    path('shareholders/withdrawal-history/', views.shareholder_withdrawal_history),
    path('shareholders/withdrawals/stats/', views.shareholder_withdrawal_stats),
    path('shareholders/withdrawals/analytics/', views.shareholder_withdrawal_analytics),
    path('shareholders/withdrawals/', views.shareholder_withdrawal_list),
    path('shareholders/withdrawals/<int:pk>/', views.shareholder_withdrawal_detail),
    path('shareholders/', views.shareholder_list),
    path('shareholders/<int:pk>/', views.shareholder_detail),
    # Transactions (super admin)
    path('transactions/stats/', views.transaction_stats),
    path('transactions/', views.transaction_list),
    path('transactions/<int:pk>/', views.transaction_detail),
    # Super Settings (super admin)
    path('super-settings/overview/', views.super_settings_overview),
    path('super-settings/dashboard-stats/', views.super_settings_dashboard_stats),
    path('super-settings/fee-income/', views.super_settings_fee_income),
    path('super-settings/', views.super_setting_detail),
    # QR Stand Orders (super admin)
    path('qr-orders/price/', views.qr_stand_order_price),
    path('qr-orders/stats/', views.qr_stand_order_stats),
    path('qr-orders/analytics/', views.qr_stand_order_analytics),
    path('qr-orders/', views.qr_stand_order_list),
    path('qr-orders/<int:pk>/', views.qr_stand_order_detail),
    path('qr-orders/<int:pk>/pay/', views.qr_stand_order_pay),
    # Notifications (super admin)
    path('notifications/stats/', views.notification_stats),
    path('notifications/', views.notification_list),
    path('notifications/<int:pk>/', views.notification_detail),
    path('notifications/<int:pk>/send/', views.notification_send),
    # Customers (super admin, for receiver picker)
    path('customers/', views.customer_list),
]
