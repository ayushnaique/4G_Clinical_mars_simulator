"""HTTP layer: thin on purpose.

Two entry points serve the same state:

* `index` renders the board as HTML and accepts ordinary form POSTs, so the
  simulator works with JavaScript disabled (Post/Redirect/Get, no resubmits).
* The `api_*` views return JSON for the enhanced front end, which animates the
  robot and plays input files one step at a time instead of reloading.

Both delegate to `services`, so there is exactly one implementation of "run a
command" behind both doors.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from robot import Direction, command_names

from . import inputs, services


def _page_context(request: HttpRequest) -> dict:
    simulation = services.load(request.session)
    context = services.view_context(simulation, services.load_log(request.session))
    input_files = inputs.list_input_files()

    # `?run=<name>` auto-runs that file. Otherwise a first-time visitor gets the
    # first file played for them, so the page opens on the simulator working.
    requested = request.GET.get("run", "")
    autoplay = None
    if requested and inputs.get_input_file(requested):
        autoplay = requested
    elif input_files and services.should_autoplay(request.session):
        autoplay = input_files[0].name

    context.update(
        commands=command_names(),
        directions=[direction.name for direction in Direction],
        input_files=input_files,
        autoplay=autoplay,
        step_delay_ms=settings.SIMULATION_STEP_DELAY_MS,
    )
    return context


@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Render the simulator; handle no-JS form submissions."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "reset":
            services.reset(request.session)
        elif action == "place":
            x, _, y = request.POST.get("cell", "").partition(",")
            services.place(request.session, x, y, request.POST.get("facing", "NORTH"))
        elif action == "file":
            input_file = inputs.get_input_file(request.POST.get("name", ""))
            if input_file is not None:
                services.run_file(request.session, input_file)
        else:
            script = request.POST.get("script") or request.POST.get("command") or ""
            if script.strip():
                services.run(request.session, script)
        return redirect("simulator:index")
    return render(request, "simulator/index.html", _page_context(request))


def _json_body(request: HttpRequest) -> dict:
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@require_POST
def api_command(request: HttpRequest) -> JsonResponse:
    """Run one or more command lines and return the new state plus the log."""
    payload = _json_body(request)
    script = str(payload.get("script") or payload.get("command") or "")
    if not script.strip():
        return JsonResponse({"error": "no command supplied"}, status=400)
    simulation, log, added = services.run(request.session, script)
    return JsonResponse(services.view_context(simulation, log, added))


@require_POST
def api_place(request: HttpRequest) -> JsonResponse:
    """Place the robot on a tile: {"x": 2, "y": 3, "facing": "EAST"}."""
    payload = _json_body(request)
    result = services.place(
        request.session, payload.get("x"), payload.get("y"), payload.get("facing", "NORTH")
    )
    if result is None:
        return JsonResponse(
            {"error": "x and y must be integers and facing a direction"}, status=400
        )
    return JsonResponse(services.view_context(*result))


@require_POST
def api_reset(request: HttpRequest) -> JsonResponse:
    simulation = services.reset(request.session)
    return JsonResponse(services.view_context(simulation, []))


@require_POST
def api_file_start(request: HttpRequest, name: str) -> JsonResponse:
    """Clear the board for a step-by-step run and return the file's commands.

    The browser then sends `lines` to `api_command` one at a time. The server
    hands over the lines (comments already stripped) so the client never has to
    parse a script itself.
    """
    input_file = inputs.get_input_file(name)
    if input_file is None:
        raise Http404("no such input file")
    simulation = services.start_file(request.session)
    body = services.view_context(simulation, [])
    body["file"] = input_file.as_dict()
    return JsonResponse(body)
