"""The seam between Django and the framework-free core.

Views do not touch session keys or build Simulation objects themselves; they
ask this module. That keeps `views.py` about HTTP and leaves one place to
change if the state ever moves from the session to a database row or Redis.
"""

from __future__ import annotations

from django.conf import settings

from robot import Direction, LogEntry, Simulation, Table, parse_int

from .inputs import InputFile

SESSION_KEY = "simulation"
LOG_KEY = "simulation_log"
# Set once any input file has been run, so the intro auto-run happens on a
# visitor's first page load only -- not again after every RESET.
AUTOPLAYED_KEY = "simulation_autoplayed"
# The session is a signed cookie, and browsers silently drop cookies over ~4KB.
# Log text echoes user input, so it is clipped before it is stored: one pasted
# line of random text would otherwise push the cookie past the limit and the
# visitor's robot would vanish on the next request.
MAX_LOG_TEXT = 60


def table_from_settings() -> Table:
    return Table(
        width=settings.SIMULATION_TABLE_WIDTH,
        height=settings.SIMULATION_TABLE_HEIGHT,
    )


def load(session) -> Simulation:
    """Rehydrate the caller's simulation, or start a fresh one."""
    stored = session.get(SESSION_KEY)
    simulation = Simulation.from_dict(stored)
    # The configured table always wins over whatever an older cookie held.
    configured = table_from_settings()
    if simulation.table != configured:
        simulation = Simulation(table=configured, state=simulation.state)
        if simulation.state.placed and not configured.contains(simulation.state.placed.position):
            simulation.reset()
    return simulation


def save(session, simulation: Simulation) -> None:
    session[SESSION_KEY] = simulation.as_dict()


def load_log(session) -> list[dict]:
    return list(session.get(LOG_KEY, []))


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LOG_TEXT else text[: MAX_LOG_TEXT - 1] + "\u2026"


def _stored(entry: LogEntry) -> dict:
    record = entry.as_dict()
    record["source"] = _clip(record["source"])
    record["message"] = _clip(record["message"])
    return record


def append_log(session, entries: list[LogEntry]) -> list[dict]:
    """Append entries to the session log, keeping only the most recent ones."""
    log = load_log(session)
    log.extend(_stored(entry) for entry in entries)
    log = log[-settings.SIMULATION_MAX_LOG_ENTRIES :]
    session[LOG_KEY] = log
    return log


def clear_log(session) -> None:
    session[LOG_KEY] = []


def run(session, script: str) -> tuple[Simulation, list[dict], int]:
    """Run one or more command lines and persist the result. The main verb.

    Returns the simulation, the (capped) session log, and how many entries this
    call added -- so a client can tell which log lines are its own without
    re-deriving which input lines were comments.
    """
    simulation = load(session)
    entries = simulation.run_script(script)
    save(session, simulation)
    log = append_log(session, entries)
    return simulation, log, len(entries)


def reset(session) -> Simulation:
    """Wipe the robot off the table and clear the log: a blank board."""
    simulation = Simulation(table=table_from_settings())
    save(session, simulation)
    clear_log(session)
    return simulation


def start_file(session) -> Simulation:
    """Prepare a step-by-step run: blank board, file marked as played.

    The robot is deliberately not placed here. The file's own first line does
    that, so the run starts exactly where the file says and by the same rules
    as everything else (a file opening with an invalid PLACE stays unplaced).
    """
    session[AUTOPLAYED_KEY] = True
    return reset(session)


def run_file(session, input_file: InputFile) -> tuple[Simulation, list[dict], int]:
    """Run a whole file in one go from a blank board (the no-JS path)."""
    start_file(session)
    return run(session, "\n".join(input_file.lines))


def place(session, x, y, facing) -> tuple[Simulation, list[dict], int] | None:
    """Place the robot on a clicked tile.

    Coordinates arrive from a form or JSON, so they are validated here rather
    than pasted into a command string: "1,2,NORTH\nMOVE" as an x value must not
    smuggle a second command in, and 2.7 must not quietly become 2. Returns None
    for unusable input. A tile off the table is not rejected here; the PLACE
    rule refuses it and logs why.
    """
    try:
        column, row = parse_int(x), parse_int(y)
        heading = Direction.parse(facing)
    except ValueError:
        return None
    return run(session, f"PLACE {column},{row},{heading.name}")


def should_autoplay(session) -> bool:
    return not session.get(AUTOPLAYED_KEY, False)


def view_context(simulation: Simulation, log: list[dict], added: int = 0) -> dict:
    """Shared payload for both the HTML template and the JSON API.

    Rows are emitted NORTH-first so a template can render them top to bottom
    while the model keeps (0,0) in the SOUTH WEST, as the brief requires. The
    coordinate flip lives here, once, instead of in the template and the JS.
    """
    snapshot = simulation.as_dict()
    robot = snapshot["robot"]
    rows = []
    for y in range(simulation.table.height - 1, -1, -1):
        rows.append(
            {
                "y": y,
                "cells": [
                    {
                        "x": x,
                        "y": y,
                        "occupied": bool(robot and robot["x"] == x and robot["y"] == y),
                    }
                    for x in range(simulation.table.width)
                ],
            }
        )
    return {
        "table": snapshot["table"],
        "robot": robot,
        "report": snapshot["report"],
        "rows": rows,
        "log": log,
        "added": added,
    }
