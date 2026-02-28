"""Auth API URL configuration."""
from django.urls import path
from core.views.auth_views import (
    login,
    logout,
    staff_profile_get,
    staff_profile_patch,
    staff_change_password,
)
from core.views.menu_views import menu_view

urlpatterns = [
    path('login/', login),
    path('logout/', logout),
    path('profile/', staff_profile_get),
    path('profile/update/', staff_profile_patch),
    path('change-password/', staff_change_password),
    path('menu/', menu_view),
]
