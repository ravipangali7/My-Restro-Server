from django.urls import path
from . import auth_views
from . import views

urlpatterns = [
    path('auth/login/', auth_views.login),
    path('auth/me/', auth_views.me),
    path('auth/logout/', auth_views.logout),
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
    path('super-settings/fee-income/', views.super_settings_fee_income),
    path('super-settings/', views.super_setting_detail),
    # QR Stand Orders (super admin)
    path('qr-orders/price/', views.qr_stand_order_price),
    path('qr-orders/stats/', views.qr_stand_order_stats),
    path('qr-orders/analytics/', views.qr_stand_order_analytics),
    path('qr-orders/', views.qr_stand_order_list),
    path('qr-orders/<int:pk>/', views.qr_stand_order_detail),
    path('qr-orders/<int:pk>/pay/', views.qr_stand_order_pay),
]
