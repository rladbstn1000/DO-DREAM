#!/usr/bin/env python3
"""Fresh GitHub-hosted CI only. Never opens the local scope, env or baseline."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "scripts/ci/compose.yml"
SERVICES = {"mysql", "redis", "chroma", "be-test", "probe"}


def project_name(env: dict[str, str], root: Path = ROOT) -> str:
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("RUNNER_OS") != "Linux"):
        raise RuntimeError("CI_GITHUB_HOSTED_LINUX_REQUIRED")
    if Path(env.get("GITHUB_WORKSPACE", "/missing")).resolve() != root.resolve():
        raise RuntimeError("CI_WORKSPACE_MISMATCH")
    values = [env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")]
    if not all(re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in values):
        raise RuntimeError("CI_RUN_ID_REQUIRED")
    return f"dodream-ci-{values[0]}-{values[1]}-integration"


def clean_environment(source: dict[str, str]) -> dict[str, str]:
    # Do not inherit Docker/Compose overrides, provider credentials, .env files,
    # proxy settings or user-selected daemon contexts from the calling shell.
    keep = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "RUNNER_TEMP"}
    env = {key: value for key, value in source.items() if key in keep}
    env.update(COMPOSE_DISABLE_ENV_FILE="1", DOCKER_HOST="unix:///var/run/docker.sock",
               DODREAM_AI_MODE="LOCAL_FAKE", LIVE_API_AUTHORIZED="false")
    return env


def run(command: list[str], env: dict[str, str], *, capture: bool = False, timeout: int = 900) -> str:
    result = subprocess.run(command, cwd=ROOT, env=env, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None, timeout=timeout)
    return result.stdout.strip() if capture else ""


def resource_ids(kind: str, project: str, env: dict[str, str]) -> list[str]:
    command = ["docker", "ps", "-aq", "--no-trunc"] if kind == "container" else ["docker", kind, "ls", "-q"]
    return run(command + ["--filter", f"label=com.docker.compose.project={project}"], env, capture=True, timeout=30).split()


def require_empty_project(project: str, env: dict[str, str]) -> None:
    for kind in ("container", "network", "volume"):
        if resource_ids(kind, project, env):
            raise RuntimeError("CI_PROJECT_ALREADY_EXISTS")


def stop_owned_containers(project: str, env: dict[str, str]) -> None:
    ids = resource_ids("container", project, env)
    if not ids:
        return
    records = json.loads(run(["docker", "inspect", *ids], env, capture=True, timeout=30))
    # Validate every target before stopping any target. No rm/down/prune occurs.
    if len(records) != len(ids):
        raise RuntimeError("CI_CONTAINER_IDENTITY_MISMATCH")
    for record in records:
        labels = record.get("Config", {}).get("Labels", {}) or {}
        if (record.get("Id") not in ids or labels.get("com.docker.compose.project") != project
                or labels.get("com.docker.compose.service") not in SERVICES):
            raise RuntimeError("CI_CONTAINER_IDENTITY_MISMATCH")
    run(["docker", "stop", *ids], env, capture=True, timeout=60)


def main() -> int:
    project = project_name(dict(os.environ))
    env = clean_environment(dict(os.environ))
    require_empty_project(project, env)
    generated = {
        "CI_MYSQL_PASSWORD": secrets.token_hex(32),
        "CI_MYSQL_ROOT_PASSWORD": secrets.token_hex(32),
        "CI_JWT_SECRET": base64.b64encode(secrets.token_bytes(64)).decode(),
        "CI_TEACHER_PASSWORD": secrets.token_hex(24),
        "CI_STUDENT_SECRET": secrets.token_hex(24),
    }
    for value in generated.values():
        print(f"::add-mask::{value}", flush=True)
    env.update(generated)
    compose = ["docker", "compose", "--env-file", "/dev/null", "--project-name", project, "--file", str(COMPOSE)]
    try:
        # Dependency downloads occur only while building. Services use an
        # internal network, no published ports, and only fresh tmpfs state.
        run(compose + ["build"], env)
        run(compose + ["up", "--detach", "--wait", "--wait-timeout", "240", "mysql", "redis", "chroma"], env, timeout=300)
        run(compose + ["run", "--no-deps", "--no-TTY", "be-test"], env, timeout=600)
        run(compose + ["run", "--no-deps", "--no-TTY", "probe"], env, timeout=90)
        print("PASS: fresh keyless backend, MySQL, Redis and Chroma contracts")
        return 0
    finally:
        # The hosted VM lifecycle disposes its own fresh tmpfs resources.
        # Never delete a volume/network/container from a user machine.
        stop_owned_containers(project, env)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.SubprocessError):
        print("FAIL: keyless CI contract; no raw environment or service logs emitted", file=sys.stderr)
        sys.exit(1)
