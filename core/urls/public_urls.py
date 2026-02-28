"""Public API URL configuration (no auth)."""
from django.urls import path
from core.views.public_views import (
    public_restaurant_list,
    public_restaurant_by_id,
    public_restaurant_by_slug,
    public_restaurant_tables,
    public_restaurant_qr,
    public_restaurant_menu,
    public_feedback_submit,
)

urlpatterns = [
    path('restaurants/', public_restaurant_list),
    path('restaurants/<int:id>/', public_restaurant_by_id),
    path('restaurant/<slug:slug>/', public_restaurant_by_slug),
    path('restaurant/<slug:slug>/tables/', public_restaurant_tables),
    path('restaurant/<slug:slug>/qr/', public_restaurant_qr),
    path('restaurant/<slug:slug>/menu/', public_restaurant_menu),
    path('restaurant/<slug:slug>/feedback/', public_feedback_submit),
]
