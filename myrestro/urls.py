from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.http import JsonResponse


def root_view(request):
    """Root URL: simple API info so / is not the admin login."""
    return JsonResponse({
        'name': 'MyRestro API',
        'api': '/api/',
        'admin': '/admin/',
    })


urlpatterns = [
    # path('', root_view),
    path('api/', include('core.urls')),
    path('admin/', admin.site.urls),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns += [
    path('', admin.site.urls),
]