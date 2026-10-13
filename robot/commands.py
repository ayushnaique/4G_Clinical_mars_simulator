"""Commands as objects, discovered through a registry.

Each command is a small class that knows three things: its name, how to parse
its arguments, and how to turn one state into the next. A decorator registers
it by name, so the parser never grows an if/else chain and adding a command
(say DIAGONAL, or UNDO) means adding one class in one file.

`apply` returns a CommandOutcome rather than mutating anything. The outcome
carries the next state *and* a human-readable note, which is what the UI's
activity log and the CLI's stdout both render.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .geometry import Direction, Position, Table
from .state import Placement, RobotState


class CommandError(ValueError):
    """Raised when a line cannot be understood as a command."""


# Plain ASCII integers only. `int()` alone would also accept "1_0", " 7 " and
# non-ASCII digits such as "\u0663", none of which a user means as a coordinate.
_INTEGER = re.compile(r"[+-]?[0-9]+")
_ARGUMENT_SEPARATOR = re.compile(r"[\s,]+")


def parse_int(token: object) -> int:
    """Strictly parse a coordinate. Raises ValueError for anything but an integer.

    Accepts an `int` (but not a `bool`, which is an int subclass) or a string of
    ASCII digits. Floats are refused rather than truncated, so 2.7 is an error,
    not a silent 2.
    """
    if isinstance(token, bool):
        raise ValueError(f"not an integer: {token!r}")
    if isinstance(token, int):
        return token
    if isinstance(token, str) and _INTEGER.fullmatch(token.strip()):
        return int(token)
    raise ValueError(f"not an integer: {preview(str(token))!r}")


def preview(text: str, limit: int = 24) -> str:
    """Shorten user input before echoing it back in a message."""
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


@dataclass(frozen=True)
class CommandOutcome:
    """The result of applying one command.

    `state` is the state afterwards (unchanged if the command was ignored).
    `accepted` says whether the command had any effect, which lets the UI
    distinguish a refused MOVE from a successful one.
    `message` is the user-facing note; `output` is set only by REPORT, so a
    caller can collect exactly the REPORT lines the brief asks for.
    """

    state: RobotState
    accepted: bool
    message: str
    output: str | None = None


class Command:
    """Base class for all commands."""

    name: str = ""

    @classmethod
    def parse(cls, argument: str) -> Command:
        """Build an instance from the raw argument text after the name."""
        if argument:
            raise CommandError(f"{cls.name} takes no arguments")
        return cls()

    def apply(self, state: RobotState, table: Table) -> CommandOutcome:
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__}>"


COMMAND_REGISTRY: dict[str, type[Command]] = {}


def register(cls: type[Command]) -> type[Command]:
    """Class decorator adding a command to the registry under its name."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a name")
    COMMAND_REGISTRY[cls.name] = cls
    return cls


def command_names() -> list[str]:
    return sorted(COMMAND_REGISTRY)


# --- concrete commands -------------------------------------------------------


@register
@dataclass(frozen=True)
class Place(Command):
    """PLACE X,Y,F -- the only command valid while the robot is off the table."""

    name = "PLACE"

    position: Position
    facing: Direction

    @classmethod
    def parse(cls, argument: str) -> Place:
        # Commas and/or any whitespace separate the three fields.
        parts = [part for part in _ARGUMENT_SEPARATOR.split(argument) if part]
        if len(parts) != 3:
            raise CommandError("PLACE expects X,Y,F (for example: PLACE 1,2,NORTH)")
        raw_x, raw_y, raw_facing = parts
        try:
            x, y = parse_int(raw_x), parse_int(raw_y)
        except ValueError:
            raise CommandError(
                f"PLACE needs whole numbers, got {preview(raw_x)!r},{preview(raw_y)!r}"
            ) from None
        try:
            facing = Direction.parse(raw_facing)
        except ValueError:
            raise CommandError(
                f"{preview(raw_facing)!r} is not a direction "
                f"({', '.join(d.name for d in Direction)})"
            ) from None
        return cls(position=Position(x, y), facing=facing)

    def apply(self, state: RobotState, table: Table) -> CommandOutcome:
        if not table.contains(self.position):
            return CommandOutcome(
                state,
                accepted=False,
                message=f"PLACE ignored: ({self.position.x},{self.position.y}) is off the table",
            )
        placement = Placement(self.position, self.facing)
        return CommandOutcome(
            state.with_placement(placement),
            accepted=True,
            message=f"Placed at {placement.report()}",
        )


class PlacedOnlyCommand(Command):
    """Shared behaviour for commands the brief says to ignore when unplaced."""

    def apply(self, state: RobotState, table: Table) -> CommandOutcome:
        if state.placed is None:
            return CommandOutcome(
                state,
                accepted=False,
                message=f"{self.name} ignored: robot is not on the table yet",
            )
        return self.apply_placed(state, state.placed, table)

    def apply_placed(self, state: RobotState, placement: Placement, table: Table) -> CommandOutcome:
        raise NotImplementedError


@register
class Move(PlacedOnlyCommand):
    """MOVE one unit forward, unless that would leave the table."""

    name = "MOVE"

    def apply_placed(self, state: RobotState, placement: Placement, table: Table) -> CommandOutcome:
        target = placement.position.translated(*placement.facing.vector)
        if not table.contains(target):
            return CommandOutcome(
                state,
                accepted=False,
                message="MOVE ignored: that would take the robot off the table",
            )
        moved = Placement(target, placement.facing)
        return CommandOutcome(
            state.with_placement(moved),
            accepted=True,
            message=f"Moved to {moved.report()}",
        )


class Turn(PlacedOnlyCommand):
    """Rotation in place. Subclasses supply how many clockwise steps to take."""

    steps: int = 0

    def apply_placed(self, state: RobotState, placement: Placement, table: Table) -> CommandOutcome:
        turned = Placement(placement.position, placement.facing.turned(self.steps))
        return CommandOutcome(
            state.with_placement(turned),
            accepted=True,
            message=f"Turned to face {turned.facing.name}",
        )


@register
class Left(Turn):
    name = "LEFT"
    steps = -1


@register
class Right(Turn):
    name = "RIGHT"
    steps = 1


@register
class Report(PlacedOnlyCommand):
    """REPORT announces X,Y,F without changing anything."""

    name = "REPORT"

    def apply_placed(self, state: RobotState, placement: Placement, table: Table) -> CommandOutcome:
        line = placement.report()
        return CommandOutcome(state, accepted=True, message=line, output=line)
