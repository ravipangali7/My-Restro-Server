# URL packages - include customer_urls, owner_urls, etc.
from django.urls import path, include

urlpatterns = [
    path('auth/', include('core.urls.auth_urls')),
    path('public/', include('core.urls.public_urls')),
    path('customer/', include('core.urls.customer_urls')),
    path('owner/', include('core.urls.owner_urls')),
    path('super_admin/', include('core.urls.super_admin_urls')),
    path('manager/', include('core.urls.manager_urls')),
    path('waiter/', include('core.urls.waiter_urls')),
    path('kitchen/', include('core.urls.kitchen_urls')),
]
