"""The robot's state, including the "not yet placed" case.

The brief says every command is discarded until a valid PLACE has run. Rather
than tracking that with a boolean flag that the rest of the code must remember
to check, absence is modelled directly: `RobotState.placed` is None until a
PLACE succeeds. Commands that need a placed robot simply return the state
unchanged when it is None, so the rule is enforced in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Direction, Position


@dataclass(frozen=True)
class Placement:
    """Where the robot is and which way it faces."""

    position: Position
    facing: Direction

    def report(self) -> str:
        return f"{self.position.x},{self.position.y},{self.facing.name}"


@dataclass(frozen=True)
class RobotState:
    """A snapshot of the simulation. `placed` is None before the first PLACE."""

    placed: Placement | None = None

    def with_placement(self, placement: Placement) -> RobotState:
        return RobotState(placed=placement)
