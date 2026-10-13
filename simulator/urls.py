"""URL map for the simulator.

The HTML page and the JSON API are separate routes rather than one view that
content-negotiates: it keeps each handler single-purpose and makes the API
usable on its own (curl, an Angular front end, a test client).
"""

from django.urls import path

from . import views

app_name = "simulator"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/command/", views.api_command, name="api-command"),
    path("api/place/", views.api_place, name="api-place"),
    path("api/reset/", views.api_reset, name="api-reset"),
    path("api/files/<slug:name>/start/", views.api_file_start, name="api-file-start"),
]
