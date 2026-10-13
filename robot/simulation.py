"""The facade the outside world talks to.

`Simulation` owns a Table and the current RobotState. Its main verb is
`run_script`, which takes one or many lines. Everything it returns is plain
data, so the Django views, the management command and the tests all drive
the same object and differ only in how they render the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from .commands import Command, CommandOutcome, parse_int
from .geometry import Direction, Position, Table
from .parser import parse_script
from .state import Placement, RobotState


@dataclass(frozen=True)
class LogEntry:
    """One line of the activity log: what was asked, and what happened."""

    source: str
    message: str
    accepted: bool
    output: str | None = None
    error: bool = False

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "message": self.message,
            "accepted": self.accepted,
            "output": self.output,
            "error": self.error,
        }


class Simulation:
    """A robot on a table. Mutable on purpose: it is the session's aggregate."""

    def __init__(self, table: Table | None = None, state: RobotState | None = None):
        self.table = table or Table()
        self.state = state or RobotState()

    # -- running commands ----------------------------------------------------

    def apply(self, command: Command) -> CommandOutcome:
        outcome = command.apply(self.state, self.table)
        self.state = outcome.state
        return outcome

    def run_script(self, text: str) -> list[LogEntry]:
        """Run a whole script, collecting one log entry per meaningful line."""
        entries: list[LogEntry] = []
        for _number, source, command, error in parse_script(text):
            if command is None:
                entries.append(
                    LogEntry(source=source, message=str(error), accepted=False, error=True)
                )
                continue
            outcome = self.apply(command)
            entries.append(
                LogEntry(
                    source=source,
                    message=outcome.message,
                    accepted=outcome.accepted,
                    output=outcome.output,
                )
            )
        return entries

    def reset(self) -> None:
        self.state = RobotState()

    # -- serialisation -------------------------------------------------------

    @property
    def report(self) -> str | None:
        return self.state.placed.report() if self.state.placed else None

    def as_dict(self) -> dict:
        """A JSON-safe snapshot: what the session stores and the API returns."""
        placed = self.state.placed
        return {
            "table": {"width": self.table.width, "height": self.table.height},
            "robot": (
                None
                if placed is None
                else {
                    "x": placed.position.x,
                    "y": placed.position.y,
                    "facing": placed.facing.name,
                }
            ),
            "report": self.report,
        }

    @classmethod
    def from_dict(cls, data: object) -> Simulation:
        """Rebuild from `as_dict` output.

        The input comes from a session, i.e. from outside the process, so this
        never raises: anything malformed falls back to a default table or to an
        unplaced robot rather than turning a bad cookie into a server error.
        """
        if not isinstance(data, dict):
            return cls()
        table = _table_from(data.get("table"))
        placement = _placement_from(data.get("robot"))
        # A session written for a larger table must not resurrect a robot
        # standing outside the current one.
        if placement is None or not table.contains(placement.position):
            return cls(table=table)
        return cls(table=table, state=RobotState(placed=placement))


def _table_from(data: object) -> Table:
    if not isinstance(data, dict):
        return Table()
    try:
        return Table(width=parse_int(data["width"]), height=parse_int(data["height"]))
    except (KeyError, ValueError):
        return Table()


def _placement_from(data: object) -> Placement | None:
    if not isinstance(data, dict):
        return None
    try:
        return Placement(
            Position(parse_int(data["x"]), parse_int(data["y"])),
            Direction.parse(data["facing"]),
        )
    except (KeyError, ValueError):
        return None
