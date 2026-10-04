import json
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from zoneinfo import ZoneInfo

import pytest

from art_guardian.adapters import HomeAssistant
from art_guardian.cli import allowed_now, dispatch, load_latch, validate_config
from art_guardian.engine import Guardian
from art_guardian.samsung import Samsung, inspect_tv
from art_guardian.storage import atomic_json, exclusive_lock


@pytest.mark.parametrize("failure", [URLError(ConnectionRefusedError()), TimeoutError()])
def test_info_reads_https_when_http_transport_fails(tmp_path, monkeypatch, failure):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        assert "payload" not in kwargs
        if url.startswith("http:"):
            raise failure
        return {"device": {"PowerState": "on"}}

    monkeypatch.setattr("art_guardian.samsung.request_json", request)
    tv = Samsung("192.0.2.10", tmp_path / "token")
    assert tv.info()["device"]["PowerState"] == "on"
    assert len(calls) == 2
    assert calls[1][0] == "https://192.0.2.10:8002/api/v2/"
    assert calls[1][1]["local_self_signed"] is True


def test_info_does_not_retry_http_response_errors(tmp_path, monkeypatch):
    calls = []

    def request(url, **kwargs):
        calls.append(url)
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr("art_guardian.samsung.request_json", request)
    with pytest.raises(RuntimeError, match="403"):
        Samsung("192.0.2.10", tmp_path / "token").info()
    assert len(calls) == 1


def test_info_stops_after_two_transport_failures(tmp_path, monkeypatch):
    calls = []

    def request(url, **kwargs):
        calls.append(url)
        raise URLError(ConnectionRefusedError())

    monkeypatch.setattr("art_guardian.samsung.request_json", request)
    with pytest.raises(URLError):
        Samsung("192.0.2.10", tmp_path / "token").info()
    assert len(calls) == 2


class Fake:
    def __init__(self, mode="standby", error=None):
        self.value, self.error, self.calls = mode, error, 0

    def mode(self):
        return self.value

    def resume(self):
        self.calls += 1
        if self.error:
            raise self.error


def test_dry_run_sends_zero_commands(tmp_path):
    fake = Fake()
    g = Guardian()
    dispatch(g, fake, fake, tmp_path / "state.json", lambda: True, False)
    assert fake.calls == 0
    assert "dry run" in g.state.latched


@pytest.mark.parametrize("mode", ["art", "tv", "unknown"])
def test_last_moment_change_cancels_dispatch(tmp_path, mode):
    fake = Fake(mode)
    g = Guardian()
    dispatch(g, fake, fake, tmp_path / "state.json", lambda: True, True)
    assert fake.calls == 0
    assert g.state.latched


def test_pause_before_dispatch_sends_nothing(tmp_path):
    fake = Fake()
    dispatch(Guardian(), fake, fake, tmp_path / "state.json", lambda: False, True)
    assert fake.calls == 0


def test_timeout_after_send_is_persisted_and_not_retried(tmp_path):
    fake = Fake(error=TimeoutError("response lost"))
    path = tmp_path / "state.json"
    g = Guardian()
    dispatch(g, fake, fake, path, lambda: True, True)
    assert fake.calls == 1
    assert "uncertain" in load_latch(path)


def test_crash_during_dispatch_leaves_inflight_latch(tmp_path):
    path = tmp_path / "state.json"

    class Crash(Fake):
        def resume(self):
            assert "in flight" in load_latch(path)
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        dispatch(Guardian(), Fake(), Crash(), path, lambda: True, True)
    assert "in flight" in load_latch(path)


def test_unwritable_state_prevents_send(tmp_path, monkeypatch):
    fake = Fake()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("art_guardian.cli.atomic_json", fail)
    with pytest.raises(OSError):
        dispatch(Guardian(), fake, fake, tmp_path / "state", lambda: True, True)
    assert fake.calls == 0


def test_corrupt_file_starts_latched(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("broken")
    assert load_latch(path)


def test_state_files_private_and_lock_exclusive(tmp_path):
    path = tmp_path / "state.json"
    atomic_json(path, {"latch": ""})
    assert path.stat().st_mode & 0o777 == 0o600
    lock = tmp_path / "lock"
    with exclusive_lock(lock), pytest.raises(RuntimeError), exclusive_lock(lock):
        pass


def test_schedule_and_pause_file(tmp_path):
    config = {"active_hours": [7, 23]}
    assert allowed_now(
        config, tmp_path, datetime(2026, 9, 8, 10, tzinfo=ZoneInfo("America/Chicago"))
    )
    assert not allowed_now(
        config, tmp_path, datetime(2026, 9, 8, 23, tzinfo=ZoneInfo("America/Chicago"))
    )
    config["active_hours"] = [22, 6]
    assert allowed_now(
        config, tmp_path, datetime(2026, 9, 8, 23, tzinfo=ZoneInfo("America/Chicago"))
    )
    assert not allowed_now(
        config, tmp_path, datetime(2026, 9, 8, 10, tzinfo=ZoneInfo("America/Chicago"))
    )
    (tmp_path / "PAUSE").touch()
    assert not allowed_now(
        config, tmp_path, datetime(2026, 9, 8, 23, tzinfo=ZoneInfo("America/Chicago"))
    )


def test_example_configs_are_observe_only():
    for path in Path("examples").glob("config.*.json"):
        config = json.loads(path.read_text())
        validate_config(config, live=False)
        with pytest.raises(ValueError, match="verified"):
            validate_config(config, live=True)


def test_ha_rejects_stale_missing_and_future_observations(tmp_path, monkeypatch):
    ha = HomeAssistant(
        {"url": "http://localhost:8123", "token_file": "token", "mode_entity": "sensor.mode"},
        tmp_path,
    )
    monkeypatch.setattr("art_guardian.adapters.time.time", lambda: 1000)
    for stamp in (None, 0, 1001, "garbage", float("nan")):
        ha.call = lambda *a, stamp=stamp: {"state": "standby", "attributes": {"observed_at": stamp}}
        assert ha.mode() == "unknown"
    ha.call = lambda *a: {"state": "art", "attributes": {"observed_at": 999}}
    assert ha.mode() == "art"


def test_standby_does_not_open_art_websocket(tmp_path):
    tv = Samsung("192.0.2.10", tmp_path / "token")
    tv.info = lambda: {"device": {"PowerState": "standby"}}

    def unexpected(*args):
        raise AssertionError("Must not query Art during standby")

    tv.art_request = unexpected
    assert tv.mode() == "standby"


def test_diagnostics_do_not_change_tv_settings(tmp_path):
    tv = Samsung("192.0.2.10", tmp_path / "token")
    tv.info = lambda: {"device": {"model": "S95H", "Token": "SECRET", "wifiMac": "SECRET"}}
    requests = []

    def request(name):
        requests.append(name)
        return {"event": "ok", "value": "on"}

    tv.art_request = request
    report = inspect_tv(tv, art=True)
    assert "SECRET" not in json.dumps(report)
    assert all(not name.startswith("set_") for name in requests)
