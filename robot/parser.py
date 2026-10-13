"""Turning text into Command objects.

Deliberately lenient about shape (case, padding, tabs, `PLACE 1, 2, NORTH`)
and strict about meaning: anything it cannot resolve to a registered command
raises CommandError rather than being silently dropped, so the caller decides
whether to report it or ignore it. Blank lines and `#` comments are skipped so
that the sample scripts can document themselves.
"""

from __future__ import annotations

from collections.abc import Iterator

from .commands import COMMAND_REGISTRY, Command, CommandError, command_names, preview


def strip_comment(line: str) -> str:
    """Drop a trailing `#` comment and surrounding whitespace."""
    return line.split("#", 1)[0].strip()


def parse_line(line: str) -> Command | None:
    """Parse one line. Returns None for blanks and comments."""
    text = strip_comment(line)
    if not text:
        return None
    # Split on the first run of any whitespace, so "PLACE\t1,2,NORTH" works too.
    name, *rest = text.split(None, 1)
    command_cls = COMMAND_REGISTRY.get(name.upper())
    if command_cls is None:
        raise CommandError(
            f"unknown command {preview(name.upper())!r} "
            f"(expected one of {', '.join(command_names())})"
        )
    return command_cls.parse(rest[0].strip() if rest else "")


def meaningful_lines(text: str) -> list[str]:
    """The lines of a script that are commands (valid or not), comments removed.

    This is what a step-by-step player walks through: one entry per thing the
    robot will be told, so a blank or comment-only line never costs a step.
    """
    return [stripped for stripped in map(strip_comment, text.splitlines()) if stripped]


def parse_script(text: str) -> Iterator[tuple[int, str, Command | None, CommandError | None]]:
    """Parse a multi-line script, yielding one tuple per meaningful line.

    Each tuple is (line number, original text, command, error). Exactly one of
    command/error is set. Errors are yielded rather than raised so that one bad
    line does not abort the rest of the script -- the brief's "ignore invalid
    input, keep going" rule applied to parsing as well as to execution.
    """
    for number, raw in enumerate(text.splitlines(), start=1):
        if not strip_comment(raw):
            continue
        try:
            command = parse_line(raw)
        except CommandError as exc:
            yield number, raw.strip(), None, exc
        else:
            if command is not None:
                yield number, raw.strip(), command, None
