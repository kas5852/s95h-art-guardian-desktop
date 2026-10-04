"""Pure recovery policy. No network access, power commands, or wall-clock assumptions."""

from dataclasses import asdict, dataclass
from typing import Literal

Mode = Literal["art", "tv", "standby", "unknown"]


@dataclass(frozen=True)
class Policy:
    # A conservative engineering margin over Samsung's general 10–15 minute guidance.
    # This does NOT detect actual panel-maintenance completion.
    maintenance_seconds: float = 1200
    stable_seconds: float = 1800
    verify_seconds: float = 120
    max_sample_gap: float = 90
    resume_after_tv: bool = True

    def __post_init__(self):
        for name in ("maintenance_seconds", "stable_seconds", "verify_seconds", "max_sample_gap"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not 0 < value < 86400:
                raise ValueError(f"{name} must be a finite number between 0 and 86400")
        if type(self.resume_after_tv) is not bool:
            raise ValueError("resume_after_tv must be boolean")


@dataclass
class State:
    # Only the failure latch survives process restarts. Timers must be freshly observed.
    latched: str = ""
    mode: Mode = "unknown"
    since: float = 0
    last_sample: float | None = None
    armed: bool = False
    pending: bool = False
    attempting: bool = False
    attempt_at: float = 0


class Guardian:
    def __init__(self, policy: Policy | None = None, latch: str = ""):
        self.policy = policy or Policy()
        self.state = State(latched=latch)

    def snapshot(self):
        return asdict(self.state)

    def trip(self, reason: str):
        self.state.latched = reason
        self.state.pending = False
        self.state.armed = False
        self.state.attempting = False

    def observe(self, mode: Mode, now: float, allowed: bool = True) -> str:
        """Return a decision; 'resume' reserves one attempt before any I/O occurs.

        Caller MUST durably write an in-flight latch before dispatching that attempt.
        now must be monotonic time. unknown invalidates all accumulated standby time.
        """
        if mode not in ("art", "tv", "standby", "unknown"):
            mode = "unknown"
        s, p = self.state, self.policy
        if s.latched:
            return "latched: " + s.latched
        gap = s.last_sample is not None and (
            now < s.last_sample or now - s.last_sample > p.max_sample_gap
        )
        s.last_sample = now
        if gap:
            if s.attempting:
                self.trip("observation gap during recovery; inspect TV before resetting")
                return "latched: " + s.latched
            s.mode, s.since = "unknown", now
            s.armed = s.pending = False

        if not allowed:
            if s.attempting:
                self.trip("recovery interrupted by schedule or pause")
                return "latched: " + s.latched
            s.armed = s.pending = False
            s.mode, s.since = "unknown", now
            return "paused"

        if s.attempting:
            if mode == "art":
                s.attempting = False
                s.mode, s.since = "art", now
                s.armed = False
                return "art observed; waiting for stability"
            if mode == "tv":
                # Do not seize the screen from a viewer. Even this transition is ambiguous.
                self.trip("TV viewing observed during recovery; no further commands")
                return "latched: " + s.latched
            if now - s.attempt_at >= p.verify_seconds:
                self.trip("art was not confirmed after the single recovery attempt")
                return "latched: " + s.latched
            return "awaiting art confirmation"

        if mode == "unknown":
            s.mode, s.since = "unknown", now
            s.armed = s.pending = False
            return "unknown; recovery cancelled"

        if mode != s.mode:
            was_armed = s.armed
            previous = s.mode
            s.mode, s.since = mode, now
            s.armed = False
            s.pending = (
                mode == "standby"
                and was_armed
                and (previous == "art" or (previous == "tv" and p.resume_after_tv))
            )

        if mode in ("art", "tv"):
            s.pending = False
            if now - s.since >= p.stable_seconds:
                s.armed = mode == "art" or p.resume_after_tv
                return "stable; armed" if s.armed else "TV recovery disabled"
            return "observing active stability"

        if not s.pending:
            return "standby without a qualified transition; leaving off"
        if now - s.since < p.maintenance_seconds:
            return "allowing uninterrupted standby"
        s.pending = False
        s.attempting = True
        s.attempt_at = now
        return "resume"
