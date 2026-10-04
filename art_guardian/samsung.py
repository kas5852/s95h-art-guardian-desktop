"""Experimental LAN client for the independently documented Samsung Art websocket.

Protocol reference: NickWaterton/samsung-tv-ws-api, commit
fe95ef1d784cd32f49bf9a07ec479576574eea07. This is an original, limited
implementation, not a claim that the S95H supports the Frame protocol.
"""

import base64
import ipaddress
import json
import ssl
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode

from .network import request_json
from .storage import atomic_json

READ_REQUESTS = (
    "api_version",
    "get_artmode_status",
    "get_artmode_settings",
    "get_auto_rotation_status",
    "get_slideshow_status",
)


def private_ipv4(value):
    ip = ipaddress.ip_address(value)
    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_unspecified:
        raise ValueError("Use the TV's private LAN IPv4 address")
    return str(ip)


class Samsung:
    def __init__(self, host, token_file: Path, port=8002, timeout=8):
        self.host = private_ipv4(host)
        self.token_file = token_file
        if port not in (8001, 8002):
            raise ValueError("TV port must be 8001 or 8002")
        self.port, self.timeout = port, timeout

    def info(self):
        # This S95H stopped accepting HTTP after a cold boot; HTTPS still worked.
        # Only retry this read on transport failure, never a setting command.
        try:
            return request_json(f"http://{self.host}:8001/api/v2/", timeout=self.timeout)
        except (URLError, ConnectionError, TimeoutError):
            return request_json(
                f"https://{self.host}:8002/api/v2/",
                timeout=self.timeout,
                local_self_signed=True,
            )

    def art_request(self, name, value=None):
        import websocket

        if name not in READ_REQUESTS and name not in ("set_artmode_status", "set_motion_timer"):
            raise ValueError("Request not supported by this limited client")
        if name == "set_artmode_status" and value != "on":
            raise ValueError("Only explicit Art Mode on is implemented")
        if name == "set_motion_timer" and value not in ("off", "60", "120", "180", "240"):
            raise ValueError("Unsupported timer test value")
        parameters = {"name": base64.b64encode(b"S95H Art Guardian").decode()}
        if self.token_file.exists():
            parameters["token"] = json.loads(self.token_file.read_text())["token"]
        scheme = "wss" if self.port == 8002 else "ws"
        url = (
            f"{scheme}://{self.host}:{self.port}/api/v2/channels/com.samsung.art-app?"
            + urlencode(parameters)
        )
        deadline = time.monotonic() + self.timeout
        connection = websocket.create_connection(
            url,
            timeout=self.timeout,
            sslopt={"cert_reqs": ssl.CERT_NONE},
            http_no_proxy=[self.host],
        )
        request_id = str(uuid.uuid4())
        sent = False
        try:
            while time.monotonic() < deadline:
                connection.settimeout(max(0.05, deadline - time.monotonic()))
                raw = connection.recv()
                if not raw:
                    raise RuntimeError("TV closed the Art channel")
                if len(raw) > 2_000_000:
                    raise RuntimeError("Art response exceeds size limit")
                message = json.loads(raw)
                event = message.get("event")
                if event in ("ms.channel.unauthorized", "ms.error"):
                    raise RuntimeError("TV denied the Art channel or does not support it")
                if event == "ms.channel.connect":
                    token = message.get("data", {}).get("token")
                    if token:
                        atomic_json(self.token_file, {"token": str(token)})
                if event == "ms.channel.ready" and not sent:
                    request = {"request": name, "id": request_id, "request_id": request_id}
                    if value is not None:
                        request["value"] = value
                    connection.send(
                        json.dumps(
                            {
                                "method": "ms.channel.emit",
                                "params": {
                                    "event": "art_app_request",
                                    "to": "host",
                                    "data": json.dumps(request),
                                },
                            }
                        )
                    )
                    sent = True
                if event == "d2d_service_message":
                    data = message.get("data", {})
                    if isinstance(data, str):
                        data = json.loads(data)
                    if data.get("request_id", data.get("id")) != request_id:
                        continue
                    if data.get("event") == "error":
                        raise RuntimeError("TV rejected the Art API request")
                    return data
            raise TimeoutError("No matching Art API response within deadline")
        finally:
            connection.close()

    def mode(self):
        info = self.info()
        power = str(info.get("device", {}).get("PowerState", "")).lower()
        # MUST be calibrated against this TV: some models report art as standby.
        if power == "standby":
            return "standby"
        if power != "on":
            return "unknown"
        art = self.art_request("get_artmode_status").get("value")
        return {"on": "art", "off": "tv"}.get(art, "unknown")

    def resume(self):
        # No KEY_POWER toggle, CEC, Wake-on-LAN, repeated keys, or blind app launching.
        self.art_request("set_artmode_status", "on")


def redacted(value):
    """Omit identifying fields and tokens from user-shareable diagnostics."""
    if isinstance(value, dict):
        return {
            k: (
                "[redacted]"
                if k.lower()
                in (
                    "token",
                    "serialnumber",
                    "wifimac",
                    "mac",
                    "duid",
                    "uuid",
                    "ip",
                    "id",
                    "name",
                    "ssid",
                    "udn",
                    "uri",
                    "developerip",
                    "deviceid",
                )
                else redacted(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redacted(item) for item in value]
    return value


def inspect_tv(tv, art=False):
    report = {"observed_at": time.time(), "recovery_validated": False}
    try:
        report["device_info"] = redacted(tv.info())
    except Exception as exc:  # noqa: BLE001 — redact all third-party transport errors
        report["device_info_error"] = type(exc).__name__
    if art:
        for name in READ_REQUESTS:
            try:
                report[name] = redacted(tv.art_request(name))
            except Exception as exc:  # noqa: BLE001 — redact all third-party transport errors
                # Exception messages can contain websocket URLs and pairing tokens.
                report[name] = {"error_type": type(exc).__name__}
    report["note"] = "No TV settings or power commands were sent. Pairing may show a TV prompt."
    return report
