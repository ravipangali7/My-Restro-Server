from django.urls import path
from . import auth_views

urlpatterns = [
    path('auth/login/', auth_views.login),
    path('auth/me/', auth_views.me),
    path('auth/logout/', auth_views.logout),
    path('auth/menu/', auth_views.menu),
]
