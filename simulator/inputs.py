"""The input files the UI can auto-run.

The `.txt` scripts in `settings.SIMULATION_INPUT_DIR` are the single source of
test data: the tests check them and the page lists them as one-click runs.
Adding a scenario means dropping a file in that folder.

Files are only ever addressed by a name taken from `list_input_files()`, never
by a path from the request, so a client cannot ask for `../config/settings.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from robot import meaningful_lines
from robot.parser import strip_comment


@dataclass(frozen=True)
class InputFile:
    name: str  # file stem, the public identifier
    title: str  # human label derived from the name
    description: str  # first comment line of the file, if any
    lines: list[str]  # the commands to play, comments and blanks removed

    @property
    def start(self) -> str | None:
        """The line the run opens with, shown so the user knows where it starts."""
        return self.lines[0] if self.lines else None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "lines": self.lines,
            "start": self.start,
        }


def _input_dir() -> Path:
    return Path(settings.SIMULATION_INPUT_DIR)


def _describe(text: str) -> str:
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if strip_comment(raw):
            break
    return ""


def _load(path: Path) -> InputFile:
    text = path.read_text(encoding="utf-8")
    return InputFile(
        name=path.stem,
        title=path.stem.replace("_", " ").replace("-", " ").upper(),
        description=_describe(text),
        lines=meaningful_lines(text),
    )


def list_input_files() -> list[InputFile]:
    directory = _input_dir()
    if not directory.is_dir():
        return []
    return [_load(path) for path in sorted(directory.glob("*.txt")) if path.is_file()]


def get_input_file(name: str) -> InputFile | None:
    """Look a file up by the public name. Unknown names return None."""
    for input_file in list_input_files():
        if input_file.name == name:
            return input_file
    return None
