"""Tests for the Django layer: the page, the API, and session persistence."""

from __future__ import annotations

import json

from django.test import Client, SimpleTestCase
from django.urls import reverse


class PageTests(SimpleTestCase):
    def test_page_renders_a_grid_of_the_configured_size(self):
        response = self.client.get(reverse("simulator:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MARS ROBOT SIMULATOR")
        # 5x5 cells, each carrying its coordinates.
        self.assertEqual(response.content.decode().count("data-x="), 25)

    def test_page_works_without_javascript(self):
        """A plain form POST must update the board and redirect (PRG)."""
        url = reverse("simulator:index")
        response = self.client.post(url, {"script": "PLACE 1,2,NORTH\nMOVE\nREPORT"})
        self.assertRedirects(response, url)
        page = self.client.get(url)
        self.assertContains(page, "1,3,NORTH")

    def test_form_reset_clears_the_board(self):
        url = reverse("simulator:index")
        self.client.post(url, {"script": "PLACE 1,2,NORTH"})
        self.client.post(url, {"action": "reset"})
        page = self.client.get(url)
        self.assertContains(page, "AWAITING PLACE COMMAND")


class ApiTests(SimpleTestCase):
    def post_script(self, script, client=None):
        client = client or self.client
        return client.post(
            reverse("simulator:api-command"),
            data=json.dumps({"script": script}),
            content_type="application/json",
        )

    def test_command_returns_the_new_state(self):
        response = self.post_script("PLACE 1,2,EAST\nMOVE\nREPORT")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["robot"], {"x": 2, "y": 2, "facing": "EAST"})
        self.assertEqual(body["report"], "2,2,EAST")

    def test_rows_are_returned_north_first_for_rendering(self):
        body = self.post_script("PLACE 0,0,NORTH").json()
        self.assertEqual(body["rows"][0]["y"], 4)
        self.assertEqual(body["rows"][-1]["y"], 0)
        self.assertTrue(body["rows"][-1]["cells"][0]["occupied"])

    def test_refused_command_is_reported_but_not_an_http_error(self):
        response = self.post_script("PLACE 4,4,NORTH\nMOVE")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["robot"], {"x": 4, "y": 4, "facing": "NORTH"})
        self.assertFalse(body["log"][-1]["accepted"])

    def test_unknown_command_is_flagged_as_an_error_entry(self):
        body = self.post_script("FLY").json()
        self.assertTrue(body["log"][-1]["error"])
        self.assertIsNone(body["robot"])

    def test_empty_script_is_a_bad_request(self):
        self.assertEqual(self.post_script("   ").status_code, 400)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("simulator:api-command"))
        self.assertEqual(response.status_code, 405)

    def test_state_persists_across_requests(self):
        self.post_script("PLACE 0,0,NORTH")
        body = self.post_script("MOVE\nREPORT").json()
        self.assertEqual(body["report"], "0,1,NORTH")

    def test_sessions_are_isolated_between_clients(self):
        other = Client()
        self.post_script("PLACE 0,0,NORTH")
        body = self.post_script("REPORT", client=other).json()
        self.assertIsNone(body["robot"])

    def test_reset_endpoint_clears_state_and_log(self):
        self.post_script("PLACE 0,0,NORTH")
        body = self.client.post(reverse("simulator:api-reset")).json()
        self.assertIsNone(body["robot"])
        self.assertEqual(body["log"], [])

    def test_session_cookie_stays_under_the_browser_limit(self):
        """Browsers drop cookies over ~4KB, which would silently lose the robot."""
        import secrets

        self.post_script("PLACE 1,1,NORTH")
        noise = "\n".join(secrets.token_urlsafe(400) for _ in range(40))
        body = self.post_script(noise).json()
        self.assertLess(len(self.client.cookies["sessionid"].value), 4096)
        self.assertEqual(body["robot"], {"x": 1, "y": 1, "facing": "NORTH"})
        self.assertEqual(self.post_script("REPORT").json()["report"], "1,1,NORTH")

    def test_log_is_capped(self):
        with self.settings(SIMULATION_MAX_LOG_ENTRIES=5):
            body = self.post_script("PLACE 0,0,NORTH\n" + "LEFT\n" * 20).json()
            self.assertEqual(len(body["log"]), 5)


class ConfigurableTableTests(SimpleTestCase):
    def test_table_size_follows_settings(self):
        with self.settings(SIMULATION_TABLE_WIDTH=3, SIMULATION_TABLE_HEIGHT=8):
            response = self.client.get(reverse("simulator:index"))
            self.assertContains(response, 'style="--cols: 3; --rows: 8;"')
            body = self.client.post(
                reverse("simulator:api-command"),
                data=json.dumps({"script": "PLACE 2,7,NORTH\nREPORT"}),
                content_type="application/json",
            ).json()
            self.assertEqual(body["report"], "2,7,NORTH")
            self.assertEqual(body["table"], {"width": 3, "height": 8})
