"""Framework-free Mars robot simulation core.

Importing this package pulls in no Django and no I/O: the same objects back
the web app, the management command and the unit tests.
"""

from .commands import (
    COMMAND_REGISTRY,
    Command,
    CommandError,
    CommandOutcome,
    command_names,
    parse_int,
    register,
)
from .geometry import Direction, Position, Table
from .parser import meaningful_lines, parse_line, parse_script
from .simulation import LogEntry, Simulation
from .state import Placement, RobotState

__all__ = [
    "COMMAND_REGISTRY",
    "Command",
    "CommandError",
    "CommandOutcome",
    "Direction",
    "LogEntry",
    "Placement",
    "Position",
    "RobotState",
    "command_names",
    "meaningful_lines",
    "parse_int",
    "Simulation",
    "Table",
    "parse_line",
    "parse_script",
    "register",
]
