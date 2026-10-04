"""One-time timer change with baseline capture, identity binding, and read-back."""

import json
import time

from .storage import atomic_json


def timer_setting(tv):
    reply = tv.art_request("get_artmode_settings")
    data = reply.get("data", [])
    settings = json.loads(data) if isinstance(data, str) else data
    return next(item for item in settings if item.get("item") == "motion_timer")


def change_timer(tv, baseline_path, requested):
    device = tv.info()["device"]
    if device.get("modelName") != "QN65S95HAFXZA":
        raise ValueError("This repair was verified only on QN65S95HAFXZA; identity does not match")
    identity = device.get("duid")
    if not identity:
        raise ValueError("Cannot bind baseline to TV identity")
    current = timer_setting(tv)
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        if baseline.get("identity") != identity:
            raise ValueError("Baseline belongs to a different TV")
    else:
        if requested == "restore":
            raise ValueError("No original setting has been saved")
        baseline = {
            "identity": identity,
            "model": device["modelName"],
            "original_timer": current,
            "recorded_at": time.time(),
        }
        atomic_json(baseline_path, baseline)
    target = baseline["original_timer"]["value"] if requested == "restore" else requested
    result = {"before": current["value"], "requested": target, "recorded_at": time.time()}
    if current["value"] != target:
        try:
            tv.art_request("set_motion_timer", target)
        except Exception as exc:  # noqa: BLE001 — read back uncertain sends instead of retrying
            result["send_error_type"] = type(exc).__name__
    result["after"] = timer_setting(tv)["value"]
    result["verified"] = result["after"] == target
    atomic_json(baseline_path.with_name("timer-last-result.json"), result)
    return result
