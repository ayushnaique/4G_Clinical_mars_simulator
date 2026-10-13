"""Tests for auto-running input files, click-to-place, and reset."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from robot import Simulation, Table
from simulator import inputs


def post_json(client, url, payload=None):
    return client.post(url, data=json.dumps(payload or {}), content_type="application/json")


def expected_reports(text: str) -> list[str]:
    """Every X,Y,F a test file's comments say it should REPORT, in order."""
    comments = "\n".join(line.split("#", 1)[1] for line in text.splitlines() if "#" in line)
    return re.findall(r"\b\d+,\d+,(?:NORTH|EAST|SOUTH|WEST)\b", comments)


class InputFileCatalogueTests(SimpleTestCase):
    def test_every_testdata_file_is_listed(self):
        names = [f.name for f in inputs.list_input_files()]
        on_disk = sorted(p.stem for p in Path(settings.SIMULATION_INPUT_DIR).glob("*.txt"))
        self.assertEqual(names, on_disk)

    def test_lines_exclude_comments_and_start_is_the_first_command(self):
        example = inputs.get_input_file("example_a")
        self.assertEqual(example.lines, ["PLACE 0,0,NORTH", "MOVE", "REPORT"])
        self.assertEqual(example.start, "PLACE 0,0,NORTH")
        self.assertIn("Brief example A", example.description)

    def test_unknown_and_traversal_names_are_not_found(self):
        for name in ["nope", "../config/settings", "example_a.txt", ""]:
            with self.subTest(name=name):
                self.assertIsNone(inputs.get_input_file(name))

    def test_files_are_read_from_the_configured_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "zigzag.txt").write_text("# Zig\nPLACE 1,1,EAST\nMOVE\n")
            with self.settings(SIMULATION_INPUT_DIR=folder):
                files = inputs.list_input_files()
        self.assertEqual([f.name for f in files], ["zigzag"])
        self.assertEqual(files[0].title, "ZIGZAG")

    def test_missing_folder_is_an_empty_list(self):
        with self.settings(SIMULATION_INPUT_DIR="/definitely/not/here"):
            self.assertEqual(inputs.list_input_files(), [])

    def test_each_file_reports_what_its_comments_promise(self):
        files = sorted(Path(settings.SIMULATION_INPUT_DIR).glob("*.txt"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=path.name):
                text = path.read_text()
                expected = expected_reports(text)
                self.assertTrue(expected, f"{path.name} does not state its expected output")
                entries = Simulation(Table(5, 5)).run_script(text)
                self.assertEqual([e.output for e in entries if e.output], expected)


class AutoRunTests(SimpleTestCase):
    def test_first_visit_autoplays_the_first_file(self):
        first = inputs.list_input_files()[0].name
        page = self.client.get(reverse("simulator:index"))
        self.assertContains(page, f'data-autoplay="{first}"')

    def test_autoplay_happens_once_per_visitor(self):
        post_json(self.client, reverse("simulator:api-file-start", args=["example_a"]))
        page = self.client.get(reverse("simulator:index"))
        self.assertNotContains(page, "data-autoplay=")

    def test_reset_does_not_retrigger_the_intro(self):
        post_json(self.client, reverse("simulator:api-file-start", args=["example_a"]))
        post_json(self.client, reverse("simulator:api-reset"))
        self.assertNotContains(self.client.get(reverse("simulator:index")), "data-autoplay=")

    def test_page_lists_each_file_with_its_starting_line(self):
        page = self.client.get(reverse("simulator:index"))
        self.assertContains(page, "STARTS: PLACE 1,2,EAST")  # example_c


class FileStartApiTests(SimpleTestCase):
    def test_start_clears_the_board_and_returns_the_lines(self):
        post_json(self.client, reverse("simulator:api-command"), {"script": "PLACE 3,3,WEST"})
        body = post_json(
            self.client, reverse("simulator:api-file-start", args=["example_c"])
        ).json()
        self.assertIsNone(body["robot"])
        self.assertEqual(body["log"], [])
        self.assertEqual(body["file"]["lines"][0], "PLACE 1,2,EAST")

    def test_stepping_through_the_lines_starts_at_the_files_first_line(self):
        start = post_json(
            self.client, reverse("simulator:api-file-start", args=["example_c"])
        ).json()
        first = post_json(
            self.client, reverse("simulator:api-command"), {"script": start["file"]["lines"][0]}
        ).json()
        self.assertEqual(first["robot"], {"x": 1, "y": 2, "facing": "EAST"})
        self.assertEqual(first["added"], 1)
        for line in start["file"]["lines"][1:]:
            last = post_json(self.client, reverse("simulator:api-command"), {"script": line}).json()
        self.assertEqual(last["report"], "3,3,NORTH")

    def test_stepping_matches_running_the_whole_file(self):
        """Stepping line by line must end where running the whole file does."""
        for input_file in inputs.list_input_files():
            with self.subTest(file=input_file.name):
                post_json(self.client, reverse("simulator:api-file-start", args=[input_file.name]))
                body = None
                for line in input_file.lines:
                    body = post_json(
                        self.client, reverse("simulator:api-command"), {"script": line}
                    ).json()
                whole = Simulation(Table(5, 5))
                whole.run_script("\n".join(input_file.lines))
                self.assertEqual(body["report"], whole.report)

    def test_unknown_file_is_404(self):
        response = post_json(self.client, reverse("simulator:api-file-start", args=["nope"]))
        self.assertEqual(response.status_code, 404)

    def test_no_js_file_run_plays_the_whole_file(self):
        url = reverse("simulator:index")
        response = self.client.post(url, {"action": "file", "name": "example_b"})
        self.assertRedirects(response, url)
        self.assertContains(self.client.get(url), "0,0,WEST")


class PlaceByClickTests(SimpleTestCase):
    def test_reset_then_click_places_on_that_tile(self):
        post_json(self.client, reverse("simulator:api-command"), {"script": "PLACE 1,1,NORTH"})
        cleared = post_json(self.client, reverse("simulator:api-reset")).json()
        self.assertIsNone(cleared["robot"])
        placed = post_json(
            self.client, reverse("simulator:api-place"), {"x": 4, "y": 0, "facing": "WEST"}
        ).json()
        self.assertEqual(placed["robot"], {"x": 4, "y": 0, "facing": "WEST"})
        self.assertEqual(placed["log"][-1]["source"], "PLACE 4,0,WEST")

    def test_every_tile_can_be_placed_on(self):
        for x in range(5):
            for y in range(5):
                body = post_json(
                    self.client, reverse("simulator:api-place"), {"x": x, "y": y, "facing": "SOUTH"}
                ).json()
                self.assertEqual(body["robot"], {"x": x, "y": y, "facing": "SOUTH"})

    def test_off_table_click_is_refused_by_the_place_rule(self):
        body = post_json(
            self.client, reverse("simulator:api-place"), {"x": 7, "y": 0, "facing": "NORTH"}
        ).json()
        self.assertIsNone(body["robot"])
        self.assertFalse(body["log"][-1]["accepted"])

    def test_bad_place_payloads_are_400(self):
        for payload in [{"x": "a", "y": 1}, {"x": 1}, {"x": 1, "y": 1, "facing": "UP"}]:
            with self.subTest(payload=payload):
                response = post_json(self.client, reverse("simulator:api-place"), payload)
                self.assertEqual(response.status_code, 400)

    def test_non_integer_coordinates_are_refused_not_truncated(self):
        for x in [2.7, True, "2.0", None]:
            with self.subTest(x=x):
                response = post_json(
                    self.client, reverse("simulator:api-place"), {"x": x, "y": 0, "facing": "NORTH"}
                )
                self.assertEqual(response.status_code, 400)

    def test_coordinates_cannot_smuggle_extra_commands(self):
        response = post_json(
            self.client,
            reverse("simulator:api-place"),
            {"x": "1,1,NORTH\nMOVE", "y": 0, "facing": "NORTH"},
        )
        self.assertEqual(response.status_code, 400)

    def test_no_js_tile_click_places_with_chosen_facing(self):
        url = reverse("simulator:index")
        response = self.client.post(url, {"action": "place", "cell": "2,3", "facing": "EAST"})
        self.assertRedirects(response, url)
        self.assertContains(self.client.get(url), "Robot at 2,3 facing EAST")

    def test_every_tile_is_a_place_button(self):
        page = self.client.get(reverse("simulator:index")).content.decode()
        self.assertEqual(page.count('form="place-form" name="cell"'), 25)
