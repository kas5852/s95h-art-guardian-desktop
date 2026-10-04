import json

import pytest

from art_guardian.repair import change_timer


class TV:
    def __init__(self):
        self.value = "240"
        self.identity = "test-tv"
        self.model = "QN65S95HAFXZA"
        self.sends = 0
        self.timeout = False

    def info(self):
        return {"device": {"modelName": self.model, "duid": self.identity}}

    def art_request(self, name, value=None):
        if name == "set_motion_timer":
            self.sends += 1
            self.value = value
            if self.timeout:
                raise TimeoutError()
            return {"value": value}
        return {"data": json.dumps([{"item": "motion_timer", "value": self.value}])}


def test_off_then_restore_preserves_first_baseline(tmp_path):
    tv = TV()
    path = tmp_path / "baseline.json"
    assert change_timer(tv, path, "off")["verified"]
    assert change_timer(tv, path, "off")["verified"]
    assert tv.sends == 1
    assert change_timer(tv, path, "restore")["after"] == "240"
    assert json.loads(path.read_text())["original_timer"]["value"] == "240"


def test_timeout_reads_back_without_resending(tmp_path):
    tv = TV()
    tv.timeout = True
    assert change_timer(tv, tmp_path / "baseline.json", "off")["verified"]
    assert tv.sends == 1


def test_different_tv_cannot_receive_old_baseline(tmp_path):
    tv = TV()
    path = tmp_path / "baseline.json"
    change_timer(tv, path, "off")
    tv.identity = "another-tv"
    with pytest.raises(ValueError, match="different TV"):
        change_timer(tv, path, "restore")
    assert tv.sends == 1


def test_unexpected_model_rejected_before_setting(tmp_path):
    tv = TV()
    tv.model = "OTHER"
    with pytest.raises(ValueError, match="identity"):
        change_timer(tv, tmp_path / "baseline.json", "off")
    assert tv.sends == 0
