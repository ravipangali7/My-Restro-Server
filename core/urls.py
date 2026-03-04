from django.urls import path
from . import auth_views
from . import views

urlpatterns = [
    path('auth/login/', auth_views.login),
    path('auth/me/', auth_views.me),
    path('auth/logout/', auth_views.logout),
    # Super admin: Owners
    path('owners/stats/', views.owner_stats),
    path('owners/search/', views.owner_search),
    path('owners/charts/kyc-distribution/', views.owner_chart_kyc_distribution),
    path('owners/charts/registration-trend/', views.owner_chart_registration_trend),
    path('owners/charts/owner-restaurant-count/', views.owner_chart_owner_restaurant_count),
    path('owners/', views.owner_list),
    path('owners/<int:pk>/', views.owner_detail),
    # Restaurants (super admin)
    path('restaurants/stats/', views.restaurant_stats),
    path('restaurants/charts/status-distribution/', views.restaurant_chart_status_distribution),
    path('restaurants/charts/new-restaurants-growth/', views.restaurant_chart_new_restaurants_growth),
    path('restaurants/charts/balance-comparison/', views.restaurant_chart_balance_comparison),
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
    path('shareholders/search/', views.shareholder_search),
    path('shareholders/charts/earnings-withdrawals-trend/', views.shareholder_chart_earnings_withdrawals_trend),
    path('shareholders/charts/monthly-payout-trend/', views.shareholder_chart_monthly_payout_trend),
    path('shareholders/withdrawal-history/', views.shareholder_withdrawal_history),
    path('shareholders/withdrawals/stats/', views.shareholder_withdrawal_stats),
    path('shareholders/withdrawals/charts/request-trend/', views.withdrawals_chart_request_trend),
    path('shareholders/withdrawals/charts/monthly-amount/', views.withdrawals_chart_monthly_amount),
    path('shareholders/withdrawals/', views.shareholder_withdrawal_list),
    path('shareholders/withdrawals/<int:pk>/', views.shareholder_withdrawal_detail),
    path('shareholders/', views.shareholder_list),
    path('shareholders/<int:pk>/', views.shareholder_detail),
    # Transactions (super admin)
    path('transactions/stats/', views.transaction_stats),
    path('transactions/', views.transaction_list),
    path('transactions/<int:pk>/', views.transaction_detail),
    # QR Stand Orders (super admin)
    path('qr-orders/price/', views.qr_stand_order_price),
    path('qr-orders/stats/', views.qr_stand_order_stats),
    path('qr-orders/charts/orders-trend/', views.qr_orders_chart_orders_trend),
    path('qr-orders/charts/revenue-trend/', views.qr_orders_chart_revenue_trend),
    path('qr-orders/charts/order-status-distribution/', views.qr_orders_chart_order_status_distribution),
    path('qr-orders/charts/restaurant-orders/', views.qr_orders_chart_restaurant_orders),
    path('qr-orders/', views.qr_stand_order_list),
    path('qr-orders/<int:pk>/', views.qr_stand_order_detail),
    path('qr-orders/<int:pk>/pay/', views.qr_stand_order_pay),
]
