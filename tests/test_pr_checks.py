"""The pull-request test check (.github/workflows/tests.yml): it only reads, and stays apart
from the daily data workflow."""
import re
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")


def concurrency_group(text):
    return re.search(r"^concurrency:\n  group: (.+)\n", text, re.M).group(1)


def test_runs_on_pull_requests_to_main_and_by_hand_never_on_a_schedule():
    on = TESTS.split("\non:\n")[1].split("\n\n")[0]
    assert re.search(r"pull_request:\n    branches: \[main\]", on)
    assert "workflow_dispatch:" in on
    assert "schedule" not in on and "cron" not in TESTS and "push:" not in on


def test_only_reads_no_secrets_no_commit_no_publishing():
    assert re.search(r"^permissions:\n  contents: read\n", TESTS, re.M)
    assert "write" not in TESTS
    assert "secrets." not in TESTS and "GH_TOKEN" not in TESTS and "GITHUB_TOKEN" not in TESTS
    for word in ("git commit", "git push", "git add", "pages", "deploy", "upload-artifact",
                 "build_events.py", "refresh_chessresults.py", "verify_published.py", "curl", "wget"):
        assert word not in TESTS.lower(), word
    assert "persist-credentials: false" in TESTS


def test_has_its_own_concurrency_group_apart_from_the_data_workflow():
    assert concurrency_group(TESTS) != concurrency_group(DAILY)
    assert concurrency_group(TESTS).startswith("pr-tests-")
    assert "tests.yml" not in DAILY  # the data workflow does not call or wait for it


def test_same_python_and_requirements_as_the_data_workflow_with_a_pip_cache():
    assert 'python-version: "3.13"' in TESTS and 'python-version: "3.13"' in DAILY
    install = "python -m pip install -r requirements.txt -r requirements-dev.txt"
    assert install in TESTS and install in DAILY
    assert "cache: pip" in TESTS
    assert "requirements.txt" in TESTS.split("cache-dependency-path:")[1]
    assert "requirements-dev.txt" in TESTS.split("cache-dependency-path:")[1]
    assert TESTS.index(install) < TESTS.index("python -m pytest -q")
    for action in ("actions/checkout", "actions/setup-python"):
        assert re.search(rf"uses: {action}@v\d+", TESTS), action
    assert re.search(r"timeout-minutes: \d+", TESTS)


def test_the_tests_cannot_reach_the_network():
    with pytest.raises(AssertionError, match="network"):
        socket.create_connection(("example.com", 443), timeout=1)
    with pytest.raises(AssertionError, match="network"):
        socket.socket().connect(("192.0.2.1", 80))
