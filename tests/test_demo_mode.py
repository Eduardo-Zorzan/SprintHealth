import unittest
from unittest.mock import patch

import devops_api
import reassignment
from demo_data import DEMO_SERVER_URL


class DemoModeTests(unittest.TestCase):
    def test_demo_combos_do_not_call_requests(self):
        with patch("devops_api.requests.get") as get_mock:
            areas = devops_api.get_area_options(DEMO_SERVER_URL, "")
            sprints = devops_api.get_sprint_options(DEMO_SERVER_URL, "", "SprintHealth\\Platform")
            dates = devops_api.get_sprint_dates(DEMO_SERVER_URL, "", "SprintHealth\\Platform", sprints[0])

        self.assertIn("SprintHealth\\Platform", areas)
        self.assertIn("SprintHealth\\Sprint 2026.15", sprints)
        self.assertEqual(("06/07/2026", "17/07/2026"), dates)
        get_mock.assert_not_called()

    def test_demo_tasks_do_not_call_requests(self):
        with patch("devops_api.requests.post") as post_mock:
            task_ids, headers = devops_api.get_tasks(
                DEMO_SERVER_URL,
                "",
                "SprintHealth\\Platform",
                "SprintHealth\\Sprint 2026.15",
                filter_members=["Ana Silva"],
            )

        self.assertEqual(["9101", "9102"], task_ids)
        self.assertIn("Authorization", headers)
        post_mock.assert_not_called()

    def test_demo_burndown_data_has_chart_payload_shape(self):
        data = devops_api.get_historical_burndown_data(
            DEMO_SERVER_URL,
            {},
            "SprintHealth\\Platform",
            "SprintHealth\\Sprint 2026.15",
            selected_members=["Ana Silva", "Bruno Costa"],
            start_date="06/07/2026",
            end_date="17/07/2026",
        )

        self.assertTrue(data["dates"])
        self.assertEqual(len(data["dates"]), len(data["actual_remaining"]))
        self.assertEqual(len(data["dates"]), len(data["remaining_capacity"]))
        self.assertIn("summary", data)
        self.assertGreater(data["summary"]["total_capacity"], 0)

    def test_demo_work_history_can_filter_members(self):
        data = devops_api.get_historical_work_history(
            DEMO_SERVER_URL,
            {},
            "SprintHealth\\Platform",
            "SprintHealth\\Sprint 2026.15",
            selected_members=["Ana Silva"],
            start_date="06/07/2026",
            end_date="17/07/2026",
        )

        self.assertEqual(["Ana Silva"], sorted(data.keys()))
        self.assertTrue(data["Ana Silva"])

    def test_demo_reassignments_do_not_call_requests(self):
        with patch("reassignment.requests.Session") as session_mock:
            events = reassignment.get_reassignments(
                ["9102", "9105"],
                DEMO_SERVER_URL,
                {},
                start_date="06/07/2026",
                end_date="17/07/2026",
            )

        self.assertEqual(2, len(events))
        self.assertEqual(["9105", "9102"], [event["task_id"] for event in events])
        session_mock.assert_not_called()

    def test_demo_reassignments_follow_selected_date_range(self):
        events = reassignment.get_reassignments(
            ["9102", "9105"],
            DEMO_SERVER_URL,
            {},
            start_date="03/02/2025",
            end_date="14/02/2025",
        )

        self.assertEqual(2, len(events))
        self.assertTrue(all("02/2025" in event["date"] for event in events))


if __name__ == "__main__":
    unittest.main()
