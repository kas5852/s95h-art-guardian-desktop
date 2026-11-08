import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "scripts" / "ci_gate.py"
CI = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
JOBS = CI["jobs"]
GATE_JOB = JOBS["all-checks-passed"]
SECURITY_JOBS = {"workflow-security", "secret-scan", "codeql", "dependency-review"}


def run_gate(results, event="push"):
    needs = {job: {"result": result, "outputs": {}} for job, result in results.items()}
    environment = {**os.environ, "NEEDS": json.dumps(needs), "EVENT": event}
    return subprocess.run(
        [sys.executable, str(GATE)], env=environment, capture_output=True, text=True, check=False
    )


def all_jobs_succeeded():
    return {job: "success" for job in GATE_JOB["needs"]}


def test_gate_passes_when_every_job_succeeded():
    outcome = run_gate(all_jobs_succeeded(), event="pull_request")

    assert outcome.returncode == 0
    assert "Every required job passed." in outcome.stdout


@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
@pytest.mark.parametrize("job", sorted(set(JOBS) - {"all-checks-passed"}))
def test_gate_fails_on_any_job_that_did_not_succeed_in_a_pull_request(job, result):
    outcome = run_gate({**all_jobs_succeeded(), job: result}, event="pull_request")

    assert outcome.returncode == 1
    assert f"These jobs did not pass:\n  {job}: {result}\n" in outcome.stdout


def test_dependency_review_may_be_skipped_only_outside_pull_requests():
    skipped = {**all_jobs_succeeded(), "dependency-review": "skipped"}

    assert run_gate(skipped, event="push").returncode == 0
    assert run_gate(skipped, event="pull_request").returncode == 1


@pytest.mark.parametrize("job", sorted(set(JOBS) - {"all-checks-passed", "dependency-review"}))
def test_no_other_job_may_be_skipped_on_push(job):
    outcome = run_gate({**all_jobs_succeeded(), job: "skipped"}, event="push")

    assert outcome.returncode == 1


def test_gate_fails_when_it_receives_no_results():
    outcome = run_gate({})

    assert outcome.returncode == 1
    assert "nothing was checked" in outcome.stdout


def test_gate_waits_on_every_other_job_in_the_workflow():
    assert sorted(GATE_JOB["needs"]) == sorted(set(JOBS) - {"all-checks-passed"})


def test_gate_includes_every_security_check():
    assert SECURITY_JOBS <= set(GATE_JOB["needs"])


def test_gate_runs_even_after_a_failure_and_cannot_be_ignored():
    assert GATE_JOB["if"] == "always()"
    assert all("continue-on-error" not in job for job in JOBS.values())
    steps = [step for job in JOBS.values() for step in job.get("steps", [])]
    assert all("continue-on-error" not in step for step in steps)


def test_only_dependency_review_is_conditional():
    conditional = {name for name, job in JOBS.items() if "if" in job}

    assert conditional == {"dependency-review", "all-checks-passed"}
    assert JOBS["dependency-review"]["if"] == "github.event_name == 'pull_request'"
