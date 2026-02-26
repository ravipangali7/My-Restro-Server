"""Kitchen API URL configuration. Kitchen dashboard: orders list and status update only."""
from django.urls import path
from core.utils import auth_required
from core.permissions import kitchen_required
from core.views.kitchen.order_views import kitchen_orders, kitchen_order_update
from core.views.in_app_notification_views import (
    in_app_notification_list_staff,
    in_app_notification_create,
    in_app_notification_recipients,
)


def _kitchen_view(view_func):
    return auth_required(kitchen_required(view_func))


urlpatterns = [
    path('orders/', _kitchen_view(kitchen_orders)),
    path('orders/<int:pk>/update/', _kitchen_view(kitchen_order_update)),
    path('in-app-notifications/', _kitchen_view(in_app_notification_list_staff)),
    path('in-app-notifications/send/', _kitchen_view(in_app_notification_create)),
    path('in-app-notifications/recipients/', _kitchen_view(in_app_notification_recipients)),
]
