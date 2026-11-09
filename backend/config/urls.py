from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({"message": "CSRF cookie set"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/csrf/", csrf_token, name="csrf-token"),
    path("api/", include("learning_api.urls")),
]