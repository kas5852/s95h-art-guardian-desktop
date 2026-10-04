"""Persistent timer repair and a 4 AM–9 AM local standby schedule."""

import argparse
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .ipcontrol import IPControl, wake
from .notifications import Notifications
from .repair import change_timer, timer_setting
from .samsung import Samsung
from .storage import atomic_json, exclusive_lock

LOGGER = logging.getLogger(__name__)


def scheduled_action(now):
    """Five-minute dispatch windows; never catch up an old overnight power-off."""
    if now.hour == 4 and now.minute < 5:
        return "standby"
    if now.hour == 9 and now.minute < 5:
        return "wake"
    return None


def quiet(now):
    return 4 <= now.hour < 9


class Service:
    def __init__(self, config, directory, tv, power, state=None):
        self.config, self.directory, self.tv, self.power = config, directory, tv, power
        self.path = directory / "service-state.json"
        self.state = state if state is not None else (
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )
        if not isinstance(self.state, dict):
            raise TypeError("Invalid service state")
        self.alerts = Notifications(config["ntfy"], directory, self.state)
        for record in self.state.get("actions", {}).values():
            if record.get("status") == "attempting":
                record["status"] = "interrupted-or-uncertain"
                self.alerts.send(
                    "interrupted-action", "S95H: interrupted power action",
                    "The controller restarted during a power action. It will not repeat "
                    "the action automatically. Please check the TV.",
                )
                self.save()

    def save(self):
        atomic_json(self.path, self.state)

    def identify(self):
        device = self.tv.info()["device"]
        target = self.config["tv"]
        if device.get("modelName") != "QN65S95HAFXZA" or device.get("duid") != target["identity"]:
            raise ValueError("TV identity does not match configured hardware")
        return str(device.get("PowerState", "unknown")).lower()

    def reserve(self, name, now):
        key = f"{now.date().isoformat()}:{name}"
        actions = self.state.setdefault("actions", {})
        if key in actions:
            if actions[key].get("status") == "attempting":
                actions[key]["status"] = "interrupted-or-uncertain"
                self.alerts.send(
                    "action-" + name, "S95H: interrupted scheduled " + name,
                    "The controller restarted during a power action. It will not repeat "
                    "the action automatically. Please check the TV.",
                )
                self.save()
            return None
        actions[key] = {"status": "attempting", "at": now.isoformat()}
        # Keep at most a month of action records. Existing alert keys are bounded below.
        self.state["actions"] = dict(sorted(actions.items())[-64:])
        self.save()
        return key

    def repair(self):
        setting = timer_setting(self.tv)
        self.state["timer"] = setting["value"]
        if setting["value"] == "240":
            result = change_timer(self.tv, self.directory / "timer-baseline.json", "off")
            self.state["last_repair"] = result
            self.state["timer"] = result["after"]
            if not result["verified"]:
                raise RuntimeError("Timer repair read-back failed")
            LOGGER.info("Repaired artwork timer: 240 -> off")
        elif setting["value"] != "off":
            self.alerts.send(
                "unexpected-timer", "S95H: unexpected artwork timer",
                "The artwork timer has an unexpected value. The service left it unchanged.",
            )

    def run_action(self, name, now):
        key = self.reserve(name, now)
        if key is None:
            return
        action = self.state["actions"][key]
        try:
            if name == "standby":
                mode = self.identify()
                if mode == "standby":
                    action["status"] = "already-standby"
                elif mode == "on":
                    self.state["protected_until_epoch"] = now.timestamp() + 1200
                    self.save()
                    if self.power.standby() != "powerOff":
                        raise RuntimeError("Power-off response did not confirm standby")
                    action["status"] = "standby-requested"
                    action["maintenance"] = "20-minute opportunity; completion not measured"
                else:
                    raise RuntimeError("Unknown TV power state")
            else:
                self.resume_art()
                action["status"] = "verified"
        except Exception as exc:  # noqa: BLE001 — ambiguous power sends are never repeated
            action["status"] = "failed-or-uncertain"
            action["error_type"] = type(exc).__name__
            LOGGER.error("Scheduled %s failed (%s)", name, type(exc).__name__)
            self.alerts.send(
                "action-" + name, "S95H: scheduled " + name + " failed",
                "The scheduled TV action failed or could not be verified. "
                "The service will not repeat power commands. Please check the TV.",
            )
        self.save()

    def resume_art(self):
        """Explicit IP wake, one optional WoL fallback, then bounded read-only polling."""
        if time.time() < self.state.get("protected_until_epoch", 0):
            raise RuntimeError("Maintenance window is still protected")
        try:
            initial = self.identify()
        except (OSError, RuntimeError):
            initial = "unreachable"
        if initial == "on":
            # Respect somebody already watching TV at 9 AM.
            art = self.wait_art_status()
            if art != "on":
                self.state["wake_note"] = "TV already in use; left viewing alone"
                return
            self.repair()
            return
        if initial not in ("standby", "unreachable"):
            raise RuntimeError("Unknown TV power state")
        try:
            if self.power.power_on() != "powerOn":
                raise RuntimeError("Power-on response was not confirmed")
            self.state["last_wake_method"] = "ip-powerOn"
        except (OSError, RuntimeError):
            # Both actions are explicit on requests, never a power toggle.
            LOGGER.warning("IP wake unavailable; sending one Wake-on-LAN fallback")
            wake(self.config["tv"]["wake_mac"])
            self.state["last_wake_method"] = "wake-on-lan-fallback"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            time.sleep(5)
            try:
                if self.identify() == "on":
                    break
            except (OSError, RuntimeError):
                continue
        else:
            raise TimeoutError("TV did not wake")
        if self.wait_art_status() != "on":
            try:
                self.tv.resume()
            except Exception as exc:  # noqa: BLE001 — verify uncertain Art sends without resending
                LOGGER.warning("Art activation response uncertain (%s)", type(exc).__name__)
        if self.wait_art_status(expected="on") != "on":
            raise RuntimeError("Art Mode read-back failed")
        self.repair()

    def wait_art_status(self, expected=None):
        """Allow the Art app to start after wake, without repeating activation commands."""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                value = self.tv.art_request("get_artmode_status").get("value")
                if value in ("on", "off") and (expected is None or value == expected):
                    return value
            except Exception as exc:  # noqa: BLE001 — transient boot-time reads may time out
                LOGGER.debug("Art app not ready (%s)", type(exc).__name__)
            time.sleep(2)
        raise TimeoutError("Art API did not become ready")

    def tick(self, now):
        self.state["heartbeat"] = now.isoformat()
        self.state["schedule_enabled"] = bool(self.config.get("schedule_enabled"))
        self.state["wake_policy"] = "ip-powerOn-first"
        if (self.directory / "PAUSE").exists():
            self.state["status"] = "paused"
            self.save()
            return
        if now.timestamp() < self.state.get("protected_until_epoch", 0):
            self.state["status"] = "maintenance-protected"
            self.save()
            return
        action = scheduled_action(now)
        if self.config.get("schedule_enabled") and action:
            self.run_action(action, now)
        if quiet(now):
            self.state["status"] = "overnight-quiet"
            self.save()
            return
        try:
            mode = self.identify()
        except ValueError:
            self.state["status"] = "identity-mismatch"
            self.alerts.send(
                "identity", "S95H: TV identity mismatch",
                "The address no longer identifies the configured TV. No settings were changed.",
            )
            self.save()
            return
        except Exception as exc:  # noqa: BLE001 — a sleeping TV can drop off the network
            self.state["status"] = "unreachable-or-standby"
            self.state["last_read_error"] = type(exc).__name__
            self.save()
            return
        self.state["power"] = mode
        if mode != "on":
            self.state["status"] = "standby" if mode == "standby" else "unknown-power"
            self.save()
            return
        try:
            self.repair()
            self.state["active_failures"] = 0
            self.state["status"] = "watching-timer"
            self.state["last_success"] = now.isoformat()
        except Exception as exc:  # noqa: BLE001 — repeated active-TV failures warrant an alert
            failures = self.state.get("active_failures", 0) + 1
            self.state["active_failures"] = failures
            self.state["status"] = "active-tv-api-error"
            LOGGER.warning("Timer check failed (%s), count=%s", type(exc).__name__, failures)
            if failures >= 3:
                self.alerts.send(
                    "timer-api", "S95H: artwork timer checks failing",
                    "The TV is awake, but three consecutive timer checks or repairs failed. "
                    "Please check TV permissions and the service log.",
                )
        self.save()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(args.config.read_text())
    root = args.config.resolve().parent
    directory = root / "private"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    zone = ZoneInfo(config.get("timezone", "America/Chicago"))
    interval = config.get("poll_seconds", 60)
    if not isinstance(interval, (int, float)) or not 30 <= interval <= 120:
        raise ValueError("poll_seconds must be 30–120")
    if config.get("schedule_enabled") and config.get("power_mapping_verified") is not True:
        raise ValueError("Schedule requires the supervised power test to be verified")
    tv = Samsung(config["tv"]["host"], directory / "tv-token.json")
    power = IPControl(tv.host, directory / "ip-control-token.json")
    with exclusive_lock(directory / "service.lock"):
        service = Service(config, directory, tv, power)
        LOGGER.info(
            "Timer watcher started; schedule=%s; wake=IP powerOn",
            bool(config.get("schedule_enabled")),
        )
        try:
            while True:
                # Only these two deployment flags can change without a restart.
                latest = json.loads(args.config.read_text())
                enabled = latest.get("schedule_enabled", False)
                if type(enabled) is not bool:
                    raise TypeError("schedule_enabled must be a boolean")
                if enabled and latest.get("power_mapping_verified") is not True:
                    raise ValueError("Schedule requires supervised power verification")
                service.config["schedule_enabled"] = enabled
                service.tick(datetime.now(zone))
                if args.once:
                    break
                time.sleep(interval)
        except Exception as exc:  # noqa: BLE001 — log a redacted fatal error before systemd restart
            LOGGER.error("Service stopped (%s)", type(exc).__name__)
            service.alerts.send(
                "service-crash", "S95H: controller stopped unexpectedly",
                "The TV controller stopped unexpectedly. systemd will attempt to restart it.",
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
