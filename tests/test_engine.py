import random

import pytest

from art_guardian.engine import Guardian, Policy


def advance(g, mode, start, duration, allowed=True):
    decisions = []
    for tick in range(start, start + duration + 1, 30):
        decisions.append(g.observe(mode, tick, allowed))
    return decisions


def ready():
    g = Guardian()
    advance(g, "art", 0, 1800)
    assert g.state.armed
    return g


def test_waits_full_maintenance_window():
    g = ready()
    assert "resume" not in advance(g, "standby", 1830, 1170)
    assert g.observe("standby", 3030) == "resume"
    assert g.observe("standby", 3060) == "awaiting art confirmation"


def test_cold_start_in_standby_never_wakes():
    assert "resume" not in advance(Guardian(), "standby", 0, 86400)


def test_unknown_never_means_off():
    g = ready()
    advance(g, "standby", 1830, 1140)
    g.observe("unknown", 3000)
    assert "resume" not in advance(g, "standby", 3030, 86400)


def test_manual_viewing_cancels_delayed_wake():
    g = ready()
    advance(g, "standby", 1830, 1140)
    assert g.observe("tv", 3000) == "observing active stability"
    assert not g.state.pending
    assert "resume" not in advance(g, "tv", 3030, 3600)


@pytest.mark.parametrize("reason", ["gap", "clock_backward", "pause"])
def test_observation_discontinuity_cancels_timer(reason):
    g = ready()
    advance(g, "standby", 1830, 1140)
    if reason == "gap":
        g.observe("standby", 4000)
        start = 4030
    elif reason == "clock_backward":
        g.observe("standby", 2000)
        start = 2030
    else:
        g.observe("standby", 3000, False)
        start = 3030
    assert "resume" not in advance(g, "standby", start, 3600)


def test_failed_wake_is_one_attempt_then_latched():
    g = ready()
    assert advance(g, "standby", 1830, 3600).count("resume") == 1
    assert g.state.latched
    assert "resume" not in advance(g, "standby", 5460, 86400)


def test_tv_mode_during_recovery_stops_commands():
    g = ready()
    advance(g, "standby", 1830, 1200)
    g.observe("tv", 3060)
    assert "TV viewing" in g.state.latched


def test_brief_art_then_reboot_cannot_rearm():
    g = ready()
    advance(g, "standby", 1830, 1200)
    assert g.observe("art", 3060) == "art observed; waiting for stability"
    assert "resume" not in advance(g, "standby", 3090, 7200)


def test_successful_four_hour_session_can_recover_again():
    g = ready()
    assert advance(g, "standby", 1830, 1200).count("resume") == 1
    advance(g, "art", 3060, 14400)
    assert advance(g, "standby", 17490, 1200).count("resume") == 1


def test_restart_preserves_latch_but_not_timing():
    g = Guardian(latch="previous attempt uncertain")
    assert "resume" not in advance(g, "art", 0, 3600)
    assert "resume" not in advance(g, "standby", 3630, 3600)
    restarted = Guardian()
    assert "resume" not in advance(restarted, "standby", 0, 7200)


def test_configurable_tv_off_recovery():
    g = Guardian(Policy(resume_after_tv=False))
    advance(g, "tv", 0, 3600)
    assert "resume" not in advance(g, "standby", 3630, 3600)


def test_bootloop_trace_24_hours_no_recovery():
    g = Guardian()
    trace = ["tv", "standby", "unknown", "art", "standby", "unknown"]
    assert all(g.observe(trace[i % len(trace)], i * 30) != "resume" for i in range(2880))


def test_random_outages_and_state_changes_never_wake_active_or_unknown():
    randomizer = random.Random(95)
    g = Guardian()
    now = 0
    for _ in range(10000):
        mode = randomizer.choice(["art", "tv", "standby", "unknown"])
        now += randomizer.choice([30, 30, 30, 300])
        decision = g.observe(mode, now)
        if decision == "resume":
            assert mode == "standby"


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), "1200"])
def test_invalid_policy_rejected(bad):
    with pytest.raises(ValueError):
        Policy(maintenance_seconds=bad)
