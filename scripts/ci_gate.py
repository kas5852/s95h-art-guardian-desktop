"""Turn the results of every CI job into one honest pass or fail.

A job passes only by succeeding. Failed, cancelled, and skipped jobs all fail
the gate. The single exception is dependency review, which GitHub can only run
on pull requests, so it may be skipped on other events.
"""

import json
import os
import sys

PULL_REQUEST_ONLY_JOBS = frozenset({"dependency-review"})


def problems(results, event):
    if not results:
        return ["The gate received no job results, so nothing was checked."]
    return [
        f"{job}: {result}"
        for job, result in sorted(results.items())
        if not acceptable(job, result, event)
    ]


def acceptable(job, result, event):
    if result == "success":
        return True
    skipped_outside_pull_request = result == "skipped" and event != "pull_request"
    return skipped_outside_pull_request and job in PULL_REQUEST_ONLY_JOBS


def main():
    needs = json.loads(os.environ["NEEDS"])
    results = {job: details["result"] for job, details in needs.items()}
    found = problems(results, os.environ["EVENT"])
    for job, result in sorted(results.items()):
        print(f"{job}: {result}")
    if found:
        print("\nThese jobs did not pass:", *found, sep="\n  ")
        sys.exit(1)
    print("\nEvery required job passed.")


if __name__ == "__main__":
    main()
