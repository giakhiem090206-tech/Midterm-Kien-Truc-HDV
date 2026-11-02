"""Run concurrency scenarios against an isolated Docker Compose test stack."""

import os
from pathlib import Path
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parent
PROJECT = f"midterm-concurrency-{uuid.uuid4().hex[:8]}"
BASE_COMPOSE = ROOT / "docker-compose.yml"
TEST_COMPOSE = ROOT / "docker-compose.test.yml"
COMPOSE_FILES = [str(BASE_COMPOSE), str(TEST_COMPOSE)]
SCENARIOS = ("concurrency1", "concurrency2")


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = ["docker", "compose", "-p", PROJECT]
    for path in COMPOSE_FILES:
        command.extend(["-f", path])
    return subprocess.run(command + list(args), cwd=ROOT, check=check)


def main() -> int:
    requested = sys.argv[1:] or list(SCENARIOS)
    if any(scenario not in SCENARIOS for scenario in requested):
        print(f"Usage: python test_concurrency.py [{'|'.join(SCENARIOS)}]")
        return 2

    env = os.environ.copy()
    env.update({
        "DEMO_GATEWAY_URL": "http://localhost:18080/api/v1",
        "TEST_COMPOSE_FILES": ";".join(COMPOSE_FILES),
        "TEST_COMPOSE_PROJECT": PROJECT,
    })
    demo_script = ROOT / "tests" / "demo_test.py"

    try:
        for index, scenario in enumerate(requested):
            compose("up", "-d", "--build", "--wait")
            subprocess.run(
                [sys.executable, str(demo_script), scenario],
                cwd=ROOT,
                env=env,
                check=True,
            )
            if index < len(requested) - 1:
                compose("down", "-v", "--remove-orphans")
    finally:
        compose("down", "-v", "--remove-orphans", check=False)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
