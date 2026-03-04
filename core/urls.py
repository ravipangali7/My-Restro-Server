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
    path('owners/', views.owner_list),
    path('owners/<int:pk>/', views.owner_detail),
    # Restaurants (super admin)
    path('restaurants/stats/', views.restaurant_stats),
    path('restaurants/', views.restaurant_list),
    path('restaurants/<int:pk>/', views.restaurant_detail),
    # KYC (super admin)
    path('kyc/stats/', views.kyc_stats),
    path('kyc/', views.kyc_list),
    # Shareholders (super admin)
    path('shareholders/stats/', views.shareholder_stats),
    path('shareholders/search/', views.shareholder_search),
    path('shareholders/withdrawal-history/', views.shareholder_withdrawal_history),
    path('shareholders/', views.shareholder_list),
    path('shareholders/<int:pk>/', views.shareholder_detail),
]
