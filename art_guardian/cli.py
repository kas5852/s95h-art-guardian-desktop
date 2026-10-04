"""Command line entry points. Nothing is installed or enabled as a background service."""

import argparse
import json
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters import HomeAssistant
from .engine import Guardian, Policy
from .repair import change_timer, timer_setting
from .samsung import Samsung, inspect_tv
from .storage import atomic_json, exclusive_lock

LOGGER = logging.getLogger(__name__)


def allowed_now(config, directory, now=None):
    if (directory / "PAUSE").exists():
        return False
    local = now or datetime.now(ZoneInfo(config.get("timezone", "America/Chicago")))
    start, end = config.get("active_hours", [7, 23])
    hour = local.hour + local.minute / 60
    return start <= hour < end if start < end else hour >= start or hour < end


def validate_config(config, live):
    hours = config.get("active_hours", [7, 23])
    if (
        not isinstance(hours, list)
        or len(hours) != 2
        or not all(type(n) is int and 0 <= n <= 24 for n in hours)
        or hours[0] == hours[1]
        or hours[0] == 24
    ):
        raise ValueError("active_hours must be two different integer hours; use [0,24] for all day")
    policy = Policy(**config.get("policy", {}))
    interval = config.get("poll_seconds", 30)
    if not isinstance(interval, (float, int)) or not 5 <= interval <= 60:
        raise ValueError("poll_seconds must be between 5 and 60")
    if interval >= policy.max_sample_gap:
        raise ValueError("poll_seconds must be smaller than max_sample_gap")
    ZoneInfo(config.get("timezone", "America/Chicago"))
    if live:
        if config.get("mapping_verified_on_this_tv") is not True:
            raise ValueError(
                "Live mode requires the TV state mapping to be verified; see docs/SETUP.md"
            )
        if policy.maintenance_seconds < 1200 or policy.stable_seconds < 1800:
            raise ValueError("Live mode requires >=20 min standby and >=30 min active stability")
    for key in ("source", "action"):
        if config.get(key, "local") not in ("local", "home_assistant"):
            raise ValueError(f"Unsupported {key}")
    return policy


def make_adapters(config, root):
    instances = {}
    for name in {config.get("source", "local"), config.get("action", "local")}:
        if name == "local":
            local = config["tv"]
            instances[name] = Samsung(
                local["host"],
                root / local.get("token_file", "private/tv-token.json"),
                local.get("port", 8002),
                local.get("timeout", 8),
            )
        else:
            instances[name] = HomeAssistant(config["home_assistant"], root)
    return instances[config.get("source", "local")], instances[config.get("action", "local")]


def read_mode(source):
    try:
        mode = source.mode()
        return mode if mode in ("art", "tv", "standby") else "unknown"
    except Exception as exc:  # noqa: BLE001 — fail closed across third-party I/O failures
        LOGGER.warning("State unavailable (%s)", type(exc).__name__)
        return "unknown"


def dispatch(guardian, source, action, state_file, is_allowed, live):
    """Reserve durably before POST/send; uncertain errors never get retried."""
    if not live:
        guardian.trip("dry run reached a recovery candidate; no command sent")
        return
    if read_mode(source) != "standby" or not is_allowed():
        guardian.trip("state, schedule, or pause changed before dispatch")
        return
    # A crash anywhere after this fsync causes the next process to start latched.
    atomic_json(
        state_file,
        {
            "latch": "previous recovery was in flight; inspect TV before resetting",
            "recorded_at": time.time(),
        },
    )
    try:
        action.resume()
    except Exception as exc:  # noqa: BLE001 — fail closed across third-party I/O failures
        guardian.trip("recovery outcome uncertain: " + type(exc).__name__)
        # Caller also checkpoints. Write here so this remains safe in isolation.
        atomic_json(state_file, {"latch": guardian.state.latched, "recorded_at": time.time()})


def load_latch(path):
    if not path.exists():
        return ""
    try:
        saved = json.loads(path.read_text())
        if not isinstance(saved.get("latch"), str):
            raise TypeError("Invalid state")
        return saved["latch"]
    except (ValueError, OSError, TypeError, AttributeError):
        return "state file unreadable; inspect before resetting"


def run(config_path, live=False, duration=0):
    config_path = config_path.resolve()
    root = config_path.parent
    config = json.loads(config_path.read_text())
    policy = validate_config(config, live)
    directory = (root / config.get("state_directory", "private")).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_file = directory / ("state-live.json" if live else "state-observe.json")
    log_handler = RotatingFileHandler(directory / "guardian.log", maxBytes=1_000_000, backupCount=3)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(), log_handler],
        force=True,
    )
    with exclusive_lock(directory / "controller.lock"):
        source, action = make_adapters(config, root)
        guardian = Guardian(policy, load_latch(state_file))
        LOGGER.info(
            "Starting %s; source=%s action=%s",
            "LIVE" if live else "OBSERVE ONLY",
            config.get("source", "local"),
            config.get("action", "local"),
        )
        started = time.monotonic()
        previous = None
        while not duration or time.monotonic() - started < duration:
            permitted = allowed_now(config, directory)
            # Don't connect to the TV during configured quiet hours or a manual pause.
            mode = read_mode(source) if permitted and not guardian.state.latched else "unknown"
            decision = guardian.observe(mode, time.monotonic(), permitted)
            if decision == "resume":
                LOGGER.info("Qualified recovery candidate")
                dispatch(
                    guardian,
                    source,
                    action,
                    state_file,
                    lambda: allowed_now(config, directory),
                    live,
                )
            latch = guardian.state.latched
            if guardian.state.attempting:
                latch = "previous recovery was in flight; inspect TV before resetting"
            atomic_json(
                state_file,
                {"latch": latch, "recorded_at": time.time(), "state": guardian.snapshot()},
            )
            current = (mode, decision, guardian.state.latched)
            if current != previous:
                LOGGER.info("mode=%s decision=%s latch=%s", *current)
                previous = current
            time.sleep(config.get("poll_seconds", 30))


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="S95H Art Guardian — hardware validation pending")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("inspect", help="Read local TV metadata; never change settings")
    doctor.add_argument("--host", required=True)
    doctor.add_argument(
        "--art", action="store_true", help="Probe Art websocket; may show pairing prompt"
    )
    doctor.add_argument("--port", type=int, choices=(8001, 8002), default=8002)
    doctor.add_argument("--timeout", type=float, default=8)
    doctor.add_argument("--output", type=Path, default=Path("private/diagnostic.json"))
    doctor.add_argument("--token-file", type=Path, default=Path("private/tv-token.json"))
    runner = commands.add_parser("run", help="Observe by default; --live enables guarded recovery")
    runner.add_argument("--config", type=Path, default=Path("config.json"))
    runner.add_argument("--live", action="store_true")
    runner.add_argument(
        "--duration", type=float, default=0, help="Seconds; 0 runs until interrupted"
    )
    read = commands.add_parser("read-timer", help="Read the artwork timer; never change it")
    read.add_argument("--host", required=True)
    read.add_argument("--token-file", type=Path, default=Path("private/tv-token.json"))
    timer = commands.add_parser("timer", help="Set the S95H artwork timer or restore its baseline")
    timer.add_argument("--host", required=True)
    timer.add_argument(
        "--value", choices=("off", "60", "120", "180", "240", "restore"), required=True
    )
    timer.add_argument("--baseline", type=Path, default=Path("private/timer-baseline.json"))
    timer.add_argument("--token-file", type=Path, default=Path("private/tv-token.json"))
    show = commands.add_parser("show-art", help="Explicitly display Samsung Art; no power toggle")
    show.add_argument("--host", required=True)
    show.add_argument("--token-file", type=Path, default=Path("private/tv-token.json"))
    reset = commands.add_parser(
        "reset-latch", help="Clear a stopped controller's latch after inspection"
    )
    reset.add_argument("--state-directory", type=Path, default=Path("private"))
    reset.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            if not 1 <= args.timeout <= 60:
                parser.error("timeout must be between 1 and 60 seconds")
            report = inspect_tv(
                Samsung(args.host, args.token_file, args.port, args.timeout), args.art
            )
            atomic_json(args.output, report)
            print(json.dumps(report, indent=2))
            print(f"Saved: {args.output.resolve()}")
        elif args.command == "read-timer":
            print(json.dumps(timer_setting(Samsung(args.host, args.token_file)), indent=2))
        elif args.command == "timer":
            result = change_timer(Samsung(args.host, args.token_file), args.baseline, args.value)
            print(json.dumps(result, indent=2))
            if not result["verified"]:
                parser.exit(1, "Timer read-back did not match the requested value.\n")
        elif args.command == "show-art":
            tv = Samsung(args.host, args.token_file)
            if tv.art_request("get_artmode_status").get("value") != "on":
                tv.resume()
            print("Art status:", tv.art_request("get_artmode_status").get("value", "unknown"))
        elif args.command == "reset-latch":
            path = args.state_directory / ("state-live.json" if args.live else "state-observe.json")
            with exclusive_lock(args.state_directory / "controller.lock"):
                atomic_json(path, {"latch": "", "recorded_at": time.time()})
            print("Latch reset. The next run still requires a fresh period of active stability.")
        else:
            if not 0 <= args.duration < float("inf"):
                parser.error("duration must be finite and nonnegative")
            run(args.config, args.live, args.duration)
    except KeyboardInterrupt:
        print("Stopped. Persistent recovery state preserved.")
    except Exception as exc:  # noqa: BLE001 — fail closed across third-party I/O failures
        # Generic exceptions may carry an authenticated URL. Only known config errors get text.
        if isinstance(exc, (ValueError, FileNotFoundError)):
            parser.exit(2, f"Configuration/file error: {exc}\n")
        parser.exit(2, f"Stopped ({type(exc).__name__}); inspect local configuration and logs.\n")


if __name__ == "__main__":
    main()
