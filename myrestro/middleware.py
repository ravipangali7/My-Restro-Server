"""
Middleware to exempt /api/ from CSRF so token-authenticated SPA requests succeed.
Must run before django.middleware.csrf.CsrfViewMiddleware.
"""

from django.conf import settings


class CorsFallbackMiddleware:
    """
    Ensure CORS headers are on the response when the request has an allowed Origin.
    Runs after corsheaders; only adds headers if the response does not already have
    Access-Control-Allow-Origin (e.g. when a proxy or error bypasses corsheaders).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.allowed_origins = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))

    def __call__(self, request):
        response = self.get_response(request)
        origin = request.META.get("HTTP_ORIGIN", "").strip()
        if not origin:
            return response
        if origin not in self.allowed_origins:
            return response
        if response.get("Access-Control-Allow-Origin"):
            return response
        response["Access-Control-Allow-Origin"] = origin
        if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
            response["Access-Control-Allow-Credentials"] = "true"
        allow_headers = getattr(settings, "CORS_ALLOW_HEADERS", None)
        if allow_headers and "Access-Control-Allow-Headers" not in response:
            response["Access-Control-Allow-Headers"] = ", ".join(allow_headers)
        if "Access-Control-Allow-Methods" not in response:
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response


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
