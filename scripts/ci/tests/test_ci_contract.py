import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("ci_integration", ROOT / "scripts/ci/integration.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class CIIsolationContract(unittest.TestCase):
    def environment(self):
        return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux",
                "GITHUB_WORKSPACE": str(ROOT), "GITHUB_RUN_ID": "123456", "GITHUB_RUN_ATTEMPT": "2"}

    def test_hosted_project_is_unique_and_local_is_refused_before_docker(self):
        self.assertEqual("dodream-ci-123456-2-integration", ci.project_name(self.environment()))
        for change in ({"GITHUB_ACTIONS": "false"}, {"RUNNER_ENVIRONMENT": "self-hosted"},
                       {"RUNNER_OS": "macOS"}, {"GITHUB_WORKSPACE": "/tmp/other"},
                       {"GITHUB_RUN_ID": "dodream-phase1"}, {"GITHUB_RUN_ATTEMPT": "../1"}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                ci.project_name(self.environment() | change)
        with patch.dict("os.environ", {}, clear=True), patch.object(ci, "run") as run:
            with self.assertRaises(RuntimeError):
                ci.main()
            run.assert_not_called()

    def test_caller_provider_keys_and_compose_overrides_are_not_inherited(self):
        env = ci.clean_environment({"PATH": "/usr/bin", "HOME": "/home/runner", "OPENAI_API_KEY": "synthetic",
                                    "COMPOSE_FILE": "compose.live.yml", "COMPOSE_PROJECT_NAME": "dodream-phase1",
                                    "DOCKER_HOST": "tcp://outside:2375", "HTTPS_PROXY": "http://outside",
                                    "LIVE_API_AUTHORIZED": "true"})
        self.assertEqual("false", env["LIVE_API_AUTHORIZED"])
        self.assertEqual("1", env["COMPOSE_DISABLE_ENV_FILE"])
        self.assertEqual("unix:///var/run/docker.sock", env["DOCKER_HOST"])
        self.assertTrue({"OPENAI_API_KEY", "COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "HTTPS_PROXY"}.isdisjoint(env))

    def test_existing_resources_block_without_mutation(self):
        for kind in ("container", "network", "volume"):
            with self.subTest(kind=kind), patch.object(ci, "resource_ids", side_effect=lambda value, *_: ["existing"] if value == kind else []), patch.object(ci, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "ALREADY_EXISTS"):
                    ci.require_empty_project("dodream-ci-1-1-integration", {})
                run.assert_not_called()

    def test_cleanup_verifies_all_identities_and_only_stops_owned_ids(self):
        project = "dodream-ci-1-1-integration"
        own = {"Id": "a", "Config": {"Labels": {"com.docker.compose.project": project, "com.docker.compose.service": "mysql"}}}
        with patch.object(ci, "resource_ids", return_value=["a"]), patch.object(ci, "run", return_value=json.dumps([own])) as run:
            ci.stop_owned_containers(project, {})
            self.assertEqual(["docker", "stop", "a"], run.call_args.args[0])
        for invalid in ({"Id": "wrong"}, {"Config": {"Labels": {"com.docker.compose.project": "dodream-phase1"}}}):
            with self.subTest(invalid=invalid), patch.object(ci, "resource_ids", return_value=["a"]), patch.object(ci, "run", return_value=json.dumps([own | invalid])) as run:
                with self.assertRaisesRegex(RuntimeError, "IDENTITY"):
                    ci.stop_owned_containers(project, {})
                self.assertEqual(1, run.call_count)

    def test_committed_ci_has_no_local_data_or_external_credential_path(self):
        compose = (ROOT / "scripts/ci/compose.yml").read_text()
        for forbidden in ("ports:", "volumes:", "secrets:", "name: dodream", ".local/", "compose.local", "compose.live"):
            self.assertNotIn(forbidden, compose)
        self.assertIn("internal: true", compose)
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text()
            self.assertIn("contents: read", text)
            self.assertNotIn("secrets.", text)
            self.assertNotIn("pull_request_target", text)
            self.assertNotIn("upload-artifact", text)
            for line in text.splitlines():
                if "uses:" in line:
                    self.assertRegex(line, r"uses: actions/[a-z-]+@[0-9a-f]{40}(?:\s|$)")

    def test_python_runtime_locks_have_exact_versions(self):
        for service in ("ai", "python-service"):
            lines = (ROOT / service / "requirements.local.lock.txt").read_text().splitlines()
            for line in lines:
                if line and not line.startswith("#"):
                    self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$")


if __name__ == "__main__":
    unittest.main()
