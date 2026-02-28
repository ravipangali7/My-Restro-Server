"""Kitchen API URL configuration. Kitchen dashboard: orders list and status update only."""
from django.urls import path
from core.utils import auth_required
from core.permissions import kitchen_required
from core.views.kitchen.order_views import kitchen_orders, kitchen_order_update


def _kitchen_view(view_func):
    return auth_required(kitchen_required(view_func))


urlpatterns = [
    path('orders/', _kitchen_view(kitchen_orders)),
    path('orders/<int:pk>/update/', _kitchen_view(kitchen_order_update)),
]
