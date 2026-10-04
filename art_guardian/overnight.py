"""Read-only, delayed checkpoints. No TV traffic between checkpoints."""

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from .repair import timer_setting
from .samsung import Samsung
from .storage import atomic_json, exclusive_lock


def timestamp():
    return datetime.now(UTC).isoformat()


def check_targets(start, delay, checks, until=None):
    """Periodic targets, including the requested final boundary exactly once."""
    if until is None:
        return [start + delay * index for index in range(1, checks + 1)]
    if until <= start:
        raise ValueError("until must be in the future")
    if until - start > 86400:
        raise ValueError("until must be within the next 24 hours")
    targets = []
    target = start + delay
    while target < until:
        targets.append(target)
        target += delay
    return targets + [until]


def parse_until(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("until must include a timezone offset, e.g. 2026-09-08T10:00:00-05:00")
    return result.timestamp()


def checkpoint(tv):
    result = {"checked_at": timestamp()}
    try:
        result["power"] = tv.info().get("device", {}).get("PowerState", "unknown")
        # If the TV is not explicitly on, leave it alone and report inconclusive.
        if result["power"] == "on":
            result["art"] = tv.art_request("get_artmode_status").get("value", "unknown")
            result["timer"] = timer_setting(tv)["value"]
        result["endpoint_ok"] = result.get("art") == "on" and result.get("timer") == "off"
    except Exception as exc:  # noqa: BLE001 — diagnostic must not expose URLs or credentials
        result["error_type"] = type(exc).__name__
        result["endpoint_ok"] = False
    result["interpretation"] = (
        "Art is on and timer is off at this checkpoint. This does not prove uninterrupted display."
        if result["endpoint_ok"]
        else "Expected endpoint state was not confirmed; no corrective commands were sent."
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument(
        "--delay", type=int, default=15000, help="Seconds between checks; default 4h10m"
    )
    parser.add_argument("--checks", type=int, default=2)
    parser.add_argument(
        "--until", help="Final check at an ISO timestamp with timezone; replaces checks"
    )
    parser.add_argument("--directory", type=Path, default=Path("private"))
    args = parser.parse_args()
    if args.delay < 60 or not 1 <= args.checks <= 3:
        parser.error("delay must be >=60 seconds and checks must be 1–3")
    os.umask(0o077)
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with exclusive_lock(directory / "overnight.lock"):
        tv = Samsung(args.host, directory / "tv-token.json")
        start_wall, start_mono = time.time(), time.monotonic()
        try:
            targets = check_targets(
                start_wall, args.delay, args.checks, parse_until(args.until) if args.until else None
            )
        except ValueError as exc:
            parser.error(str(exc))
        report = {
            "started_at": timestamp(),
            "pid": os.getpid(),
            "status": "waiting",
            "interval_seconds": args.delay,
            "planned_checks": len(targets),
            "final_check_at": datetime.fromtimestamp(targets[-1], UTC).isoformat(),
            "routine_disabled_before_start": (directory / "routine-disabled-confirmed").exists(),
            "checkpoints": [],
            "note": "No TV requests between checkpoints; no wake or setting commands at any time.",
            "limitation": "Periodic read requests may influence undocumented inactivity behavior. "
            "This tests reported settings and sampled state, not an input-free four-hour run.",
        }
        path = directory / "overnight-report.json"
        if path.exists():
            archive = directory / "monitor-history"
            archive.mkdir(exist_ok=True, mode=0o700)
            path.replace(archive / f"overnight-{time.time_ns()}.json")
        atomic_json(path, report)
        print(json.dumps(report), flush=True)
        for index, target in enumerate(targets, 1):
            # Wait in short slices; only this worker waits, not the interactive agent.
            while time.time() < target:
                time.sleep(min(60, max(0.1, target - time.time())))
            if args.until and time.time() > targets[-1] + 5:
                report["status"] = "complete; final deadline missed"
                report["finished_at"] = timestamp()
                report["note"] = (
                    "Final deadline missed, possibly due to computer sleep. No late TV request sent."
                )
                atomic_json(path, report)
                break
            # If the Mac slept across multiple targets, coalesce missed observations.
            if index < len(targets) and time.time() >= targets[index]:
                continue
            result = checkpoint(tv)
            result["scheduled_at"] = datetime.fromtimestamp(target, UTC).isoformat()
            result["elapsed_wall_seconds"] = time.time() - start_wall
            result["elapsed_monotonic_seconds"] = time.monotonic() - start_mono
            result["routine_disabled_confirmed_at_check"] = (
                directory / "routine-disabled-confirmed"
            ).exists()
            report["checkpoints"].append(result)
            report["status"] = "complete" if index == len(targets) else "waiting"
            atomic_json(path, report)
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
