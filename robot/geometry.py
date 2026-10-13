"""Value objects describing *where* things are: positions, headings, tables.

Nothing in this module knows about commands, Django or I/O. Everything is
immutable, so a state transition always produces a new object rather than
mutating a shared one -- that is what lets the web layer keep a history of
states and replay them without defensive copying.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class Position:
    """A point on the table grid. (0, 0) is the SOUTH WEST corner."""

    x: int
    y: int

    def translated(self, dx: int, dy: int) -> Position:
        return Position(self.x + dx, self.y + dy)


class Direction(Enum):
    """A compass heading plus the unit vector it advances along.

    The enum is declared in clockwise order (N -> E -> S -> W) so that turning
    is a rotation over the member list rather than a lookup table that has to
    be edited in four places. Adding, say, 8-way movement means adding members
    in clockwise order and nothing else.
    """

    NORTH = (0, 1)
    EAST = (1, 0)
    SOUTH = (0, -1)
    WEST = (-1, 0)

    def __init__(self, dx: int, dy: int) -> None:
        self.dx = dx
        self.dy = dy

    @property
    def vector(self) -> tuple[int, int]:
        return (self.dx, self.dy)

    def turned(self, steps: int) -> Direction:
        """Rotate `steps` increments clockwise; negative steps turn left."""
        members = list(Direction)
        return members[(members.index(self) + steps) % len(members)]

    @classmethod
    def parse(cls, token: str) -> Direction:
        """Case-insensitive lookup. Raises ValueError on an unknown heading."""
        if not isinstance(token, str):
            raise ValueError(f"unknown direction: {token!r}")
        try:
            return cls[token.strip().upper()]
        except KeyError:
            raise ValueError(f"unknown direction: {token!r}") from None


@dataclass(frozen=True)
class Table:
    """The surface the robot may occupy.

    Dimensions are data, not constants, so the 5x5 of the brief is a default
    and not an assumption baked into the movement rules.
    """

    width: int = 5
    height: int = 5

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError("table must be at least 1x1")

    def contains(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height
