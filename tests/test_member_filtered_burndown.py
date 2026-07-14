import unittest
from datetime import date
from unittest.mock import patch

import devops_api


class ODataMemberFilterTests(unittest.TestCase):
    def test_historical_filter_without_members_has_no_assignee_clause(self):
        query_filter = devops_api._historical_filter(
            "Project\\Area",
            "Project\\Sprint 1",
            date(2026, 7, 1),
            date(2026, 7, 10),
        )

        self.assertNotIn("AssignedTo/UserName", query_filter)
        self.assertNotIn("AssignedTo/UserEmail", query_filter)

    def test_assignee_filter_escapes_and_deduplicates_members(self):
        assignee_filter = devops_api._odata_assignee_filter([
            "O'Brien",
            "  o'brien  ",
            "",
            "alice@example.com",
        ])

        self.assertIn("AssignedTo/UserName eq 'O''Brien'", assignee_filter)
        self.assertIn("AssignedTo/UserEmail eq 'O''Brien'", assignee_filter)
        self.assertIn("AssignedTo/UserName eq 'alice@example.com'", assignee_filter)
        self.assertEqual(assignee_filter.count("O''Brien"), 2)

    def test_historical_filter_with_members_includes_name_and_email(self):
        query_filter = devops_api._historical_filter(
            "Project\\Area",
            "Project\\Sprint 1",
            date(2026, 7, 1),
            date(2026, 7, 10),
            selected_members=["Alice"],
        )

        self.assertIn("AssignedTo/UserName eq 'Alice'", query_filter)
        self.assertIn("AssignedTo/UserEmail eq 'Alice'", query_filter)


class HistoricalBurndownSourceTests(unittest.TestCase):
    def setUp(self):
        self.base_args = (
            "https://dev.azure.com/org/project",
            {"Authorization": "Basic token"},
            "Project\\Area",
            "Project\\Sprint 1",
        )
        self.start_date = date(2026, 7, 1)
        self.end_date = date(2026, 7, 10)

    @patch("devops_api._query_historical_snapshots_wiql")
    @patch("devops_api._query_historical_burndown_odata")
    def test_selected_members_use_analytics_when_available(self, odata_mock, wiql_mock):
        rows = [{"DateSK": 20260701, "RemainingWork": 8.0}]
        odata_mock.return_value = rows

        result = devops_api._get_historical_burndown_rows(
            *self.base_args,
            selected_members=["Alice"],
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual(rows, result)
        self.assertEqual(["Alice"], odata_mock.call_args.kwargs["selected_members"])
        wiql_mock.assert_not_called()

    @patch("devops_api._query_historical_snapshots_wiql")
    @patch("devops_api._query_historical_burndown_odata")
    def test_selected_members_fall_back_to_wiql_when_analytics_fails(self, odata_mock, wiql_mock):
        fallback_rows = [{"DateSK": 20260701, "RemainingWork": 5.0}]
        odata_mock.side_effect = devops_api.AnalyticsUnavailable("metadata missing")
        wiql_mock.return_value = fallback_rows

        result = devops_api._get_historical_burndown_rows(
            *self.base_args,
            selected_members=["Alice"],
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual(fallback_rows, result)
        wiql_mock.assert_called_once()

    @patch("devops_api._query_historical_snapshots_wiql")
    @patch("devops_api._query_historical_burndown_odata")
    def test_selected_members_fall_back_to_wiql_on_generic_analytics_error(self, odata_mock, wiql_mock):
        fallback_rows = [{"DateSK": 20260701, "RemainingWork": 5.0}]
        odata_mock.side_effect = RuntimeError("unexpected analytics error")
        wiql_mock.return_value = fallback_rows

        result = devops_api._get_historical_burndown_rows(
            *self.base_args,
            selected_members=["Alice"],
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual(fallback_rows, result)
        wiql_mock.assert_called_once()

    @patch("devops_api._query_historical_snapshots_wiql")
    @patch("devops_api._query_historical_burndown_odata")
    def test_selected_members_empty_analytics_result_does_not_fall_back(self, odata_mock, wiql_mock):
        odata_mock.return_value = []

        result = devops_api._get_historical_burndown_rows(
            *self.base_args,
            selected_members=["Alice"],
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual([], result)
        wiql_mock.assert_not_called()

    @patch("devops_api._query_historical_snapshots_wiql")
    @patch("devops_api._query_historical_burndown_odata")
    def test_unfiltered_empty_analytics_result_still_falls_back(self, odata_mock, wiql_mock):
        fallback_rows = [{"DateSK": 20260701, "RemainingWork": 5.0}]
        odata_mock.return_value = []
        wiql_mock.return_value = fallback_rows

        result = devops_api._get_historical_burndown_rows(
            *self.base_args,
            selected_members=None,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        self.assertEqual(fallback_rows, result)
        wiql_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
