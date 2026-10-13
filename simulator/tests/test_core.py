"""Tests for the framework-free core.

These import nothing from Django on purpose -- if the simulation rules ever
start needing the framework to be tested, the separation has leaked.
"""

from __future__ import annotations

import unittest

from robot import Direction, Position, Simulation, Table, parse_int
from robot.commands import CommandError, Place
from robot.parser import meaningful_lines, parse_line


class DirectionTests(unittest.TestCase):
    def test_turning_right_four_times_returns_to_start(self):
        for direction in Direction:
            self.assertEqual(direction.turned(4), direction)

    def test_left_and_right_are_inverses(self):
        for direction in Direction:
            self.assertEqual(direction.turned(1).turned(-1), direction)

    def test_clockwise_order(self):
        self.assertEqual(Direction.NORTH.turned(1), Direction.EAST)
        self.assertEqual(Direction.NORTH.turned(-1), Direction.WEST)

    def test_parse_is_case_insensitive(self):
        self.assertEqual(Direction.parse("  south "), Direction.SOUTH)
        with self.assertRaises(ValueError):
            Direction.parse("UPWARDS")


class TableTests(unittest.TestCase):
    def test_contains_respects_bounds(self):
        table = Table(5, 5)
        self.assertTrue(table.contains(Position(0, 0)))
        self.assertTrue(table.contains(Position(4, 4)))
        self.assertFalse(table.contains(Position(5, 4)))
        self.assertFalse(table.contains(Position(-1, 0)))

    def test_non_square_tables_are_supported(self):
        table = Table(width=3, height=7)
        self.assertTrue(table.contains(Position(2, 6)))
        self.assertFalse(table.contains(Position(3, 6)))

    def test_degenerate_table_rejected(self):
        with self.assertRaises(ValueError):
            Table(0, 5)


class ParserTests(unittest.TestCase):
    def test_place_accepts_messy_whitespace_and_case(self):
        command = parse_line("  place  1 , 2 ,  north  ")
        self.assertIsInstance(command, Place)
        self.assertEqual(command.position, Position(1, 2))
        self.assertEqual(command.facing, Direction.NORTH)

    def test_comments_and_blank_lines_are_skipped(self):
        self.assertIsNone(parse_line("   "))
        self.assertIsNone(parse_line("# just a note"))
        self.assertIsNotNone(parse_line("MOVE # trailing comment"))

    def test_unknown_command_raises(self):
        with self.assertRaises(CommandError):
            parse_line("FLY")

    def test_malformed_place_raises(self):
        for bad in ["PLACE 1,2", "PLACE a,b,NORTH", "PLACE 1,2,UP", "PLACE 1,2,3,4"]:
            with self.subTest(bad=bad), self.assertRaises(CommandError):
                parse_line(bad)

    def test_tabs_and_mixed_separators_are_accepted(self):
        for line in ["PLACE\t1,2,NORTH", "PLACE 1\t2\tNORTH", "\tplace 1 2 north"]:
            with self.subTest(line=line):
                command = parse_line(line)
                self.assertEqual(command.position, Position(1, 2))
                self.assertEqual(command.facing, Direction.NORTH)

    def test_coordinates_must_be_plain_integers(self):
        # int() alone would accept the first two and silently mean 10 and 3.
        for bad in ["PLACE 1_0,0,NORTH", "PLACE \u0663,0,NORTH", "PLACE 2.5,0,NORTH"]:
            with self.subTest(bad=bad), self.assertRaises(CommandError):
                parse_line(bad)

    def test_negative_coordinates_parse_and_are_then_refused_by_the_table(self):
        sim = Simulation(Table(5, 5))
        entries = sim.run_script("PLACE -1,+2,NORTH")
        self.assertFalse(entries[0].accepted)
        self.assertIn("off the table", entries[0].message)

    def test_error_messages_do_not_echo_huge_input(self):
        with self.assertRaises(CommandError) as caught:
            parse_line("Z" * 5000)
        self.assertLess(len(str(caught.exception)), 120)

    def test_meaningful_lines_drop_comments_and_blanks(self):
        text = "# header\n\nPLACE 0,0,NORTH   # start\n  move\n#\nFLY\n"
        self.assertEqual(meaningful_lines(text), ["PLACE 0,0,NORTH", "move", "FLY"])

    def test_commands_reject_stray_arguments(self):
        with self.assertRaises(CommandError):
            parse_line("MOVE 3")


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(Table(5, 5))

    def run_script(self, text):
        return [e.output for e in self.sim.run_script(text) if e.output is not None]

    # --- the three worked examples from the brief ---------------------------

    def test_brief_example_a(self):
        self.assertEqual(self.run_script("PLACE 0,0,NORTH\nMOVE\nREPORT"), ["0,1,NORTH"])

    def test_brief_example_b(self):
        self.assertEqual(self.run_script("PLACE 0,0,NORTH\nLEFT\nREPORT"), ["0,0,WEST"])

    def test_brief_example_c(self):
        script = "PLACE 1,2,EAST\nMOVE\nMOVE\nLEFT\nMOVE\nREPORT"
        self.assertEqual(self.run_script(script), ["3,3,NORTH"])

    # --- the rules ----------------------------------------------------------

    def test_commands_before_first_place_are_discarded(self):
        self.assertEqual(self.run_script("MOVE\nLEFT\nRIGHT\nREPORT"), [])
        self.assertIsNone(self.sim.report)

    def test_place_outside_the_table_is_ignored(self):
        self.sim.run_script("PLACE 5,5,NORTH\nPLACE -1,0,NORTH")
        self.assertIsNone(self.sim.report)

    def test_invalid_place_does_not_dislodge_a_placed_robot(self):
        self.assertEqual(self.run_script("PLACE 1,1,NORTH\nPLACE 9,9,SOUTH\nREPORT"), ["1,1,NORTH"])

    def test_move_off_each_edge_is_ignored(self):
        cases = [
            ("PLACE 0,4,NORTH\nMOVE\nREPORT", "0,4,NORTH"),
            ("PLACE 4,0,EAST\nMOVE\nREPORT", "4,0,EAST"),
            ("PLACE 0,0,SOUTH\nMOVE\nREPORT", "0,0,SOUTH"),
            ("PLACE 0,0,WEST\nMOVE\nREPORT", "0,0,WEST"),
        ]
        for script, expected in cases:
            with self.subTest(script=script):
                sim = Simulation(Table(5, 5))
                outputs = [e.output for e in sim.run_script(script) if e.output]
                self.assertEqual(outputs, [expected])

    def test_valid_commands_still_work_after_a_refused_move(self):
        # Facing SOUTH, a MOVE off the south edge is refused; turning left
        # (counterclockwise) then faces EAST, and that move must succeed.
        script = "PLACE 0,0,SOUTH\nMOVE\nLEFT\nMOVE\nREPORT"
        self.assertEqual(self.run_script(script), ["1,0,EAST"])

    def test_a_refused_command_is_logged_as_not_accepted(self):
        entries = self.sim.run_script("PLACE 0,0,SOUTH\nMOVE")
        self.assertTrue(entries[0].accepted)
        self.assertFalse(entries[1].accepted)
        self.assertIn("off the table", entries[1].message)

    def test_a_bad_line_does_not_abort_the_script(self):
        entries = self.sim.run_script("PLACE 0,0,NORTH\nFLY\nMOVE\nREPORT")
        self.assertTrue(entries[1].error)
        self.assertEqual(entries[-1].output, "0,1,NORTH")

    def test_robot_can_traverse_the_whole_table(self):
        self.sim.run_script("PLACE 0,0,NORTH\n" + "MOVE\n" * 4 + "RIGHT\n" + "MOVE\n" * 4)
        self.assertEqual(self.sim.report, "4,4,EAST")

    def test_reset_clears_the_robot(self):
        self.sim.run_script("PLACE 2,2,NORTH")
        self.sim.reset()
        self.assertIsNone(self.sim.report)


class ParseIntTests(unittest.TestCase):
    def test_accepts_ints_and_digit_strings(self):
        self.assertEqual(parse_int(3), 3)
        self.assertEqual(parse_int(" -4 "), -4)

    def test_refuses_everything_else(self):
        for bad in [True, 2.7, "2.0", "", "1e3", None, [1]]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_int(bad)


class SerialisationTests(unittest.TestCase):
    def test_round_trip_preserves_state(self):
        sim = Simulation(Table(5, 5))
        sim.run_script("PLACE 3,1,WEST")
        restored = Simulation.from_dict(sim.as_dict())
        self.assertEqual(restored.report, "3,1,WEST")
        self.assertEqual(restored.table, sim.table)

    def test_unplaced_round_trip(self):
        restored = Simulation.from_dict(Simulation().as_dict())
        self.assertIsNone(restored.report)

    def test_corrupt_payloads_degrade_to_an_empty_table(self):
        corrupt = [
            None,
            {},
            [],
            "junk",
            {"robot": {"x": "?", "y": 1, "facing": "NORTH"}},
            {"robot": {"x": 1, "y": 1, "facing": 7}},
            {"robot": ["not", "a", "dict"]},
            {"table": {"width": "wide", "height": 5}, "robot": None},
            {"table": {"width": 0, "height": 5}},
            {"table": "5x5"},
        ]
        for payload in corrupt:
            with self.subTest(payload=payload):
                self.assertIsNone(Simulation.from_dict(payload).report)

    def test_robot_outside_a_shrunken_table_is_dropped(self):
        payload = {
            "table": {"width": 2, "height": 2},
            "robot": {"x": 4, "y": 4, "facing": "NORTH"},
        }
        self.assertIsNone(Simulation.from_dict(payload).report)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
