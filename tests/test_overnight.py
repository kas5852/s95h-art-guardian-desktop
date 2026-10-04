from datetime import UTC, datetime

import pytest

from art_guardian.overnight import check_targets, checkpoint, parse_until


def test_final_boundary_included_without_duplicates():
    assert check_targets(0, 900, 2, 1800) == [900, 1800]
    assert check_targets(0, 900, 2, 2000) == [900, 1800, 2000]
    assert check_targets(0, 900, 2, 100) == [100]
    assert check_targets(0, 900, 2) == [900, 1800]


def test_until_requires_timezone_and_future_boundary():
    assert (
        parse_until("2026-09-08T10:00:00-05:00") == datetime(2026, 9, 8, 15, tzinfo=UTC).timestamp()
    )
    with pytest.raises(ValueError, match="timezone"):
        parse_until("2026-09-08T10:00:00")
    with pytest.raises(ValueError, match="future"):
        check_targets(100, 60, 2, 99)
    with pytest.raises(ValueError, match="24 hours"):
        check_targets(100, 60, 2, 100000)


class TV:
    def __init__(self, power="on", timer="off"):
        self.power, self.timer, self.requests = power, timer, []

    def info(self):
        return {"device": {"PowerState": self.power}}

    def art_request(self, request):
        self.requests.append(request)
        if request == "get_artmode_status":
            return {"value": "on"}
        if request == "get_artmode_settings":
            return {"data": [{"item": "motion_timer", "value": self.timer}]}
        raise AssertionError("Unexpected request")


def test_reset_timer_is_reported_and_never_repaired():
    tv = TV(timer="240")
    result = checkpoint(tv)
    assert result["timer"] == "240"
    assert result["endpoint_ok"] is False
    assert tv.requests == ["get_artmode_status", "get_artmode_settings"]


def test_standby_is_left_untouched():
    tv = TV(power="standby")
    result = checkpoint(tv)
    assert not result["endpoint_ok"]
    assert not tv.requests


def test_unreachable_device_reported_without_retry():
    class Unreachable:
        def info(self):
            raise TimeoutError("PRIVATE ADDRESS")

    result = checkpoint(Unreachable())
    assert result["error_type"] == "TimeoutError"
    assert "PRIVATE" not in str(result)
