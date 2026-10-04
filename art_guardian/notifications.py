"""ntfy alerts, deduplicated and rate limited in the controller's durable state."""

import logging
import time
from pathlib import Path
from urllib.parse import urlsplit

from .network import request_json
from .storage import atomic_json

LOGGER = logging.getLogger(__name__)


class Notifications:
    def __init__(self, config, directory, state, *, state_file="service-state.json"):
        self.config, self.directory, self.state = config, directory, state
        self.path = directory / state_file
        url = config.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("ntfy requires an HTTPS topic URL without embedded credentials")
        if parsed.query or parsed.fragment or parsed.path in ("", "/"):
            raise ValueError("ntfy requires a plain topic URL")

    def send(self, key, title, message, *, priority=4, once=False):
        now = time.time()
        prior = self.state.setdefault("alerts", {}).get(key, {})
        if prior and (once and prior.get("delivered") or now - prior.get("attempted", 0) < 3600):
            return False
        # Reserve before HTTP; a crash may lose an alert, but cannot flood the phone.
        record = {"attempted": now, "delivered": False}
        self.state["alerts"][key] = record
        atomic_json(self.path, self.state)
        try:
            token = None
            if self.config.get("token_file"):
                token = Path(self.config["token_file"]).read_text().strip()
            reply = request_json(
                self.config["url"].rsplit("/", 1)[0],
                token=token,
                payload={
                    "topic": self.config["url"].rsplit("/", 1)[1],
                    "title": title,
                    "message": message,
                    "priority": priority,
                    "tags": ["tv", "warning"],
                },
                timeout=10,
            )
            record["delivered"] = bool(reply.get("id"))
            if not record["delivered"]:
                raise RuntimeError("ntfy did not acknowledge the message")
        except Exception as exc:  # noqa: BLE001 — endpoint URLs and tokens stay out of logs
            LOGGER.error("Notification failed (%s)", type(exc).__name__)
        atomic_json(self.path, self.state)
        return record["delivered"]
