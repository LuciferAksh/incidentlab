"""Retain upstream routes and serve only the local fixture media directory."""

from django.conf import settings
from django.urls import re_path
from django.views.static import serve
from urls import urlpatterns as upstream_patterns

urlpatterns = [
    *upstream_patterns,
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
