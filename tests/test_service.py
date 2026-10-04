from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from art_guardian.service import Service, scheduled_action

ZONE = ZoneInfo("America/Chicago")


def at(hour, minute=0, day=2):
    return datetime(2026, 10, day, hour, minute, tzinfo=ZONE)


class TV:
    def __init__(self):
        self.calls = []
        self.power = "on"
        self.timer = "240"

    def info(self):
        self.calls.append("info")
        return {"device": {"modelName": "QN65S95HAFXZA", "duid": "test-tv",
                           "PowerState": self.power}}

    def art_request(self, name, value=None):
        self.calls.append(name)
        if name == "set_motion_timer":
            self.timer = value
            return {"value": value}
        if name == "get_artmode_settings":
            return {"data": [{"item": "motion_timer", "value": self.timer}]}
        return {"value": "on"}


class Power:
    def __init__(self):
        self.calls = 0
        self.error = False

    def standby(self):
        self.calls += 1
        if self.error:
            raise TimeoutError()
        return "powerOff"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr("art_guardian.service.time.time", lambda: at(12).timestamp())
    config = {"tv": {"identity": "test-tv"}, "ntfy": {"url": "https://notify.example.invalid/example-topic"},
              "schedule_enabled": True}
    s = Service(config, tmp_path, TV(), Power())
    s.alerts.send = lambda *a, **k: True
    return s


def test_dispatch_windows_and_no_late_standby_catchup():
    assert scheduled_action(at(4, 4)) == "standby"
    assert scheduled_action(at(4, 5)) is None
    assert scheduled_action(at(8)) is None
    assert scheduled_action(at(9, 4)) == "wake"
    assert scheduled_action(at(9, 5)) is None


def test_overnight_sends_no_tv_requests(service):
    for hour in (4, 5, 6, 7, 8):
        service.tick(at(hour, 10))
    assert service.tv.calls == []
    assert service.power.calls == 0


def test_standby_is_once_per_day_even_after_restart(service):
    service.tick(at(4))
    assert service.power.calls == 1
    new = Service(service.config, service.directory, service.tv, service.power)
    new.tick(at(4, 1))
    assert service.power.calls == 1


def test_uncertain_power_off_is_not_repeated(service):
    service.power.error = True
    service.tick(at(4))
    service.tick(at(4, 1))
    assert service.power.calls == 1
    assert service.state["actions"]["2026-10-02:standby"]["status"] == "failed-or-uncertain"


def test_active_timer_reset_is_repaired_and_not_written_again(service):
    service.tick(at(12))
    service.tick(at(12, 1))
    assert service.tv.timer == "off"
    assert service.tv.calls.count("set_motion_timer") == 1
    assert service.power.calls == 0


def test_standby_is_never_woken_by_timer_watcher(service):
    service.tv.power = "standby"
    service.tick(at(12))
    assert service.tv.calls == ["info"]
    assert service.power.calls == 0


def test_pause_and_protected_window_send_no_requests(service):
    pause = service.directory / "PAUSE"
    pause.touch()
    service.tick(at(12))
    pause.unlink()
    service.state["protected_until_epoch"] = at(12, 20).timestamp()
    service.tick(at(12))
    assert service.tv.calls == []
    assert service.power.calls == 0


def test_wake_is_reserved_before_dispatch_and_not_repeated(service):
    calls = []

    def resume():
        assert service.state["actions"]["2026-10-02:wake"]["status"] == "attempting"
        calls.append("wake")
        raise TimeoutError()

    service.resume_art = resume
    service.tick(at(9))
    service.tick(at(9, 1))
    assert calls == ["wake"]


def test_no_power_command_if_durable_reservation_fails(service, monkeypatch):
    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("art_guardian.service.atomic_json", fail)
    with pytest.raises(OSError):
        service.tick(at(4))
    assert service.power.calls == 0


def test_identity_mismatch_blocks_timer_and_power(service):
    service.config["tv"]["identity"] = "wrong-tv"
    service.tick(at(12))
    assert service.state["status"] == "identity-mismatch"
    assert service.tv.calls == ["info"]
    service.tick(at(4))
    assert service.power.calls == 0


def test_wake_refuses_to_interrupt_an_unfinished_maintenance_window(service):
    service.state["protected_until_epoch"] = at(12, 20).timestamp()
    with pytest.raises(RuntimeError, match="protected"):
        service.resume_art()
    assert service.tv.calls == []


def test_restart_flags_interrupted_action_even_in_protected_window(service, monkeypatch):
    service.state["actions"] = {"2026-10-02:standby": {"status": "attempting"}}
    service.state["protected_until_epoch"] = at(4, 20).timestamp()
    service.save()
    messages = []
    monkeypatch.setattr(
        "art_guardian.service.Notifications.send", lambda *a, **k: messages.append(a)
    )
    new = Service(service.config, service.directory, service.tv, service.power)
    new.tick(at(4, 1))
    assert new.state["actions"]["2026-10-02:standby"]["status"] == "interrupted-or-uncertain"
    assert len(messages) == 1
    assert service.tv.calls == []
    assert service.power.calls == 0


def test_ip_wake_activates_art_and_repairs_timer_without_wol(service, monkeypatch):
    service.tv.power = "standby"
    calls = []
    art = ["off"]
    original = service.tv.art_request

    def request(name, value=None):
        if name == "get_artmode_status":
            return {"value": art[0]}
        return original(name, value)

    def power_on():
        calls.append("ip-on")
        service.tv.power = "on"
        return "powerOn"

    def resume():
        calls.append("art-on")
        art[0] = "on"

    def unexpected_wol(*args):
        raise AssertionError("Successful IP wake must not send WoL")

    service.tv.art_request = request
    service.tv.resume = resume
    service.power.power_on = power_on
    monkeypatch.setattr("art_guardian.service.wake", unexpected_wol)
    monkeypatch.setattr("art_guardian.service.time.sleep", lambda *a: None)
    service.resume_art()
    assert calls == ["ip-on", "art-on"]
    assert service.tv.timer == "off"
    assert service.state["last_wake_method"] == "ip-powerOn"


def test_unavailable_ip_wake_uses_one_explicit_wol_fallback(service, monkeypatch):
    service.tv.power = "standby"
    service.config["tv"]["wake_mac"] = "00:11:22:33:44:55"
    calls = []

    def power_on():
        calls.append("ip-on")
        raise TimeoutError()

    def wol(mac):
        calls.append("wol")
        service.tv.power = "on"

    service.power.power_on = power_on
    monkeypatch.setattr("art_guardian.service.wake", wol)
    monkeypatch.setattr("art_guardian.service.time.sleep", lambda *a: None)
    service.resume_art()
    assert calls == ["ip-on", "wol"]
    assert service.state["last_wake_method"] == "wake-on-lan-fallback"


def test_already_watching_tv_at_nine_is_not_interrupted(service):
    original = service.tv.art_request
    service.tv.art_request = lambda n, v=None: (
        {"value": "off"} if n == "get_artmode_status" else original(n, v)
    )
    service.resume_art()
    assert service.tv.calls == ["info"]
    assert service.tv.timer == "240"
