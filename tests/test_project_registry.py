from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gladr.core.paths import create_local_project, list_registered_projects, set_active_project


class ProjectRegistryTests(unittest.TestCase):
    def test_create_local_project_registers_and_scaffolds_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)

            context = create_local_project(project_id="demo_project", label="Demo Project", repo_root=repo_root)

            self.assertEqual(context.project_id, "demo_project")
            self.assertEqual(context.project_root, (repo_root / "projects" / "demo_project").resolve())
            self.assertTrue((context.project_root / "project.json").exists())
            self.assertTrue(context.paths.canonical_manifests_outputs_dir.exists())
            self.assertTrue(context.paths.analysis_artifacts_outputs_dir.exists())

            registry = list_registered_projects(repo_root)
            self.assertEqual(registry["active_project"], "demo_project")
            self.assertEqual(registry["projects"][0]["id"], "demo_project")
            self.assertEqual(registry["projects"][0]["path"], "projects/demo_project")
            self.assertTrue(registry["projects"][0]["exists"])

    def test_set_active_project_switches_registered_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            create_local_project(project_id="first_project", label="First", repo_root=repo_root)
            create_local_project(project_id="second_project", label="Second", repo_root=repo_root)

            context = set_active_project("first_project", repo_root)

            self.assertEqual(context.project_id, "first_project")
            registry = list_registered_projects(repo_root)
            self.assertEqual(registry["active_project"], "first_project")
            active = {project["id"]: project["is_active"] for project in registry["projects"]}
            self.assertTrue(active["first_project"])
            self.assertFalse(active["second_project"])

    def test_rejects_unsafe_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                create_local_project(project_id="../bad", repo_root=Path(directory))


if __name__ == "__main__":
    unittest.main()
