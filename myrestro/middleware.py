"""
Middleware to exempt /api/ from CSRF so token-authenticated SPA requests succeed.
Must run before django.middleware.csrf.CsrfViewMiddleware.
"""


class CsrfExemptApiMiddleware:
    """Mark the view as csrf_exempt when the request path is under /api/."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path.startswith("/api/"):
            view_func.csrf_exempt = True
        return None
