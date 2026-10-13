"""`manage.py simulate` -- the brief's file/stdin interface.

The brief asks for commands read from a file or standard input. That is the
same simulation the web page drives, so this command is a thin adapter: read
lines, feed them to `Simulation`, print what REPORT produced.

    ./manage.py simulate testdata/example_a.txt
    cat testdata/example_a.txt | ./manage.py simulate
    ./manage.py simulate --verbose testdata/edge_cases.txt
"""

from __future__ import annotations

import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from robot import Simulation, Table


class Command(BaseCommand):
    help = "Run robot commands from a file or standard input."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "path",
            nargs="?",
            help="File of commands. Reads standard input when omitted.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print the outcome of every command, not just REPORT output.",
        )
        parser.add_argument(
            "--width",
            type=int,
            default=settings.SIMULATION_TABLE_WIDTH,
            help="Table width (default from settings).",
        )
        parser.add_argument(
            "--height",
            type=int,
            default=settings.SIMULATION_TABLE_HEIGHT,
            help="Table height (default from settings).",
        )

    def handle(self, *args, **options) -> None:
        path = options["path"]
        if path:
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
            except OSError as exc:
                raise CommandError(f"cannot read {path}: {exc.strerror}") from exc
        else:
            text = sys.stdin.read()

        try:
            table = Table(options["width"], options["height"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        simulation = Simulation(table=table)
        entries = simulation.run_script(text)

        reported: list[str] = []
        for entry in entries:
            if entry.output is not None:
                reported.append(entry.output)
            if options["verbose"]:
                style = (
                    self.style.ERROR
                    if entry.error
                    else self.style.SUCCESS
                    if entry.accepted
                    else self.style.WARNING
                )
                self.stdout.write(f"{entry.source:<20} {style(entry.message)}")

        if options["verbose"] and reported:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("REPORT output:"))
        for line in reported:
            self.stdout.write(line)
