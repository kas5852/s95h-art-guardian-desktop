from art_guardian.notifications import Notifications
from art_guardian.storage import atomic_json


def test_failed_notifications_do_not_flood_and_can_be_retried(tmp_path, monkeypatch):
    calls = []
    now = [10000]
    monkeypatch.setattr("art_guardian.notifications.time.time", lambda: now[0])

    def send(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError()
        return {"id": "received"}

    monkeypatch.setattr("art_guardian.notifications.request_json", send)
    state = {}
    alerts = Notifications({"url": "https://notify.example.invalid/example-topic"}, tmp_path, state)
    assert not alerts.send("failure", "TV failure", "Check the TV", once=True)
    assert not alerts.send("failure", "TV failure", "Check the TV", once=True)
    assert len(calls) == 1
    now[0] += 3600
    assert alerts.send("failure", "TV failure", "Check the TV", once=True)
    now[0] += 3600
    assert not alerts.send("failure", "TV failure", "Check the TV", once=True)
    assert len(calls) == 2


def test_systemd_failure_alert_cannot_overwrite_action_history(tmp_path, monkeypatch):
    path = tmp_path / "service-state.json"
    atomic_json(path, {"actions": {"today:wake": {"status": "attempting"}}})
    before = path.read_bytes()
    monkeypatch.setattr("art_guardian.notifications.request_json", lambda *a, **k: {"id": "ok"})
    alerts = Notifications(
        {"url": "https://notify.example.invalid/example-topic"}, tmp_path, {},
        state_file="failure-notifications.json",
    )
    assert alerts.send("systemd-failure", "TV service failed", "Check service")
    assert path.read_bytes() == before
