"""Root URL configuration: everything lives under the simulator app."""

from django.urls import include, path

urlpatterns = [
    path("", include("simulator.urls")),
]
