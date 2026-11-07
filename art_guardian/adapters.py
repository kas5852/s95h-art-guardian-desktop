"""Optional Home Assistant source and scene actuator; credentials stay in a local file."""

import ipaddress
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

from .network import request_json


def loopback(hostname):
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class HomeAssistant:
    """A long-lived Home Assistant token is sent on every call, so the transport matters."""

    def __init__(self, config, root: Path):
        self.config = config
        self.url = config["url"].rstrip("/")
        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Home Assistant URL must use http or https")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use a plain Home Assistant URL without embedded credentials")
        if (
            parsed.scheme == "http"
            and not loopback(parsed.hostname)
            and config.get("allow_insecure_http") is not True
        ):
            raise ValueError(
                "Refusing to send a Home Assistant token over plain http to a remote host; "
                'use https, or set "allow_insecure_http": true to accept LAN eavesdropping'
            )
        self.token_file = (root / config["token_file"]).resolve()

    def call(self, path, payload=None):
        token = self.token_file.read_text().strip()
        if not token or "\n" in token:
            raise ValueError("Invalid Home Assistant token file")
        return request_json(self.url + "/api/" + path, token=token, payload=payload)

    def mode(self):
        entity = self.config["mode_entity"]
        state = self.call("states/" + quote(entity, safe=""))
        # observed_at must come from a producer that actually checks TV state.
        # Neither HA API reachability nor a cached state's age proves TV health.
        stamp = state.get("attributes", {}).get("observed_at")
        try:
            observed = float(stamp)
        except (TypeError, ValueError):
            try:
                observed = datetime.fromisoformat(str(stamp)).timestamp()
            except ValueError:
                return "unknown"
        age = time.time() - observed
        if not 0 <= age <= self.config.get("max_age_seconds", 60):
            return "unknown"
        return self.config.get("state_map", {"art": "art", "tv": "tv", "standby": "standby"}).get(
            state.get("state"), "unknown"
        )

    def resume(self):
        scene = self.config["art_scene"]
        if not scene.startswith("scene.") or len(scene.split(".")) != 2:
            raise ValueError("art_scene must name one Home Assistant scene entity")
        self.call("services/scene/turn_on", {"entity_id": scene})
