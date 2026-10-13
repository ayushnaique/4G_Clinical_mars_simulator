"""Tests for `manage.py simulate`, the brief's file/stdin interface."""

from __future__ import annotations

import io
import re
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase


def simulate(*args: str, stdin: str | None = None) -> list[str]:
    out = io.StringIO()
    if stdin is None:
        call_command("simulate", *args, stdout=out)
    else:
        with mock.patch("sys.stdin", io.StringIO(stdin)):
            call_command("simulate", *args, stdout=out)
    return out.getvalue().split()


def expected_output(path: Path) -> list[str]:
    """Every X,Y,F a test file's comments say it should REPORT, in order."""
    comments = "\n".join(
        line.split("#", 1)[1] for line in path.read_text().splitlines() if "#" in line
    )
    return re.findall(r"\b\d+,\d+,(?:NORTH|EAST|SOUTH|WEST)\b", comments)


class SimulateCommandTests(SimpleTestCase):
    def test_each_input_file_reports_what_its_comments_promise(self):
        files = sorted(Path(settings.SIMULATION_INPUT_DIR).glob("*.txt"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=path.name):
                expected = expected_output(path)
                self.assertTrue(expected, f"{path.name} does not state its expected output")
                self.assertEqual(simulate(str(path)), expected)

    def test_reads_standard_input(self):
        self.assertEqual(simulate(stdin="PLACE 0,0,NORTH\nMOVE\nREPORT\n"), ["0,1,NORTH"])

    def test_table_size_flags(self):
        self.assertEqual(
            simulate("--width", "2", "--height", "9", stdin="PLACE 1,8,EAST\nMOVE\nREPORT\n"),
            ["1,8,EAST"],
        )

    def test_missing_file_is_a_clean_error(self):
        with self.assertRaisesMessage(CommandError, "cannot read"):
            simulate("testdata/does-not-exist.txt")

    def test_degenerate_table_is_a_clean_error(self):
        with self.assertRaisesMessage(CommandError, "at least 1x1"):
            simulate("--width", "0", stdin="")
