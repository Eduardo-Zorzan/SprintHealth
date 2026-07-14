import os
import tempfile
import unittest
from unittest.mock import patch

import config
import devops_api


class ComboCacheTests(unittest.TestCase):
    def test_save_combos_cache_replaces_existing_values(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                config.save_combos_cache(
                    ["Project\\Old Area", "Project\\Other Area"],
                    ["Project\\Sprint 1"],
                )
                config.save_combos_cache(
                    ["Project\\New Area"],
                    ["Project\\Sprint 2", "Project\\Sprint 3"],
                )

                self.assertEqual(
                    {
                        "areas": ["Project\\New Area"],
                        "sprints": ["Project\\Sprint 2", "Project\\Sprint 3"],
                    },
                    config.load_combos_cache(),
                )
            finally:
                os.chdir(original_cwd)

    def test_load_combos_cache_defaults_to_empty_lists(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                self.assertEqual({"areas": [], "sprints": []}, config.load_combos_cache())
            finally:
                os.chdir(original_cwd)


class SprintOptionsRefreshTests(unittest.TestCase):
    @patch("devops_api.get_iterations")
    @patch("devops_api._get_team_iterations")
    def test_sprint_options_can_force_project_iteration_refresh(self, team_iterations_mock, iterations_mock):
        team_iterations_mock.side_effect = Exception("team lookup failed")
        iterations_mock.return_value = {
            "path": "Project",
            "children": [
                {
                    "path": "Project\\Sprint 2",
                    "attributes": {
                        "startDate": "2026-07-01T00:00:00Z",
                        "finishDate": "2026-07-14T00:00:00Z",
                    },
                    "children": [],
                }
            ],
        }

        result = devops_api.get_sprint_options(
            "https://dev.azure.com/org/project",
            "token",
            "Project\\Area",
            force_refresh=True,
        )

        self.assertEqual(["Project\\Sprint 2"], result)
        iterations_mock.assert_called_once_with(
            "https://dev.azure.com/org/project",
            "token",
            "Project\\Area",
            force_refresh=True,
        )


if __name__ == "__main__":
    unittest.main()
