"""Small, explicitly paired Samsung consumer IP Control client.

Protocol reference: Samsung's Consumer TV IP Command List and the inspected
ha-samsungtv-smart implementation. No implicit pairing or command retries.
"""

import http.client
import json
import re
import socket
import ssl
from pathlib import Path

from .samsung import private_ipv4
from .storage import atomic_json


class IPControl:
    def __init__(self, host, token_file: Path, timeout=8):
        self.host = private_ipv4(host)
        self.token_file = token_file
        self.timeout = timeout

    def request(self, method, values=None, *, pairing=False):
        if method not in ("createAccessToken", "powerControl"):
            raise ValueError("Unsupported IP Control method")
        if pairing != (method == "createAccessToken"):
            raise ValueError("Pairing must be requested explicitly")
        if values and values not in ({"power": "powerOff"}, {"power": "powerOn"}):
            raise ValueError("Only explicit power-on and power-off are implemented")
        body = {"jsonrpc": "2.0", "id": 1, "method": method}
        if not pairing:
            token = json.loads(self.token_file.read_text())["token"]
            body["params"] = {"AccessToken": token, **(values or {})}
        payload = json.dumps(body).encode()
        connection = http.client.HTTPSConnection(
            self.host, 1516, timeout=self.timeout, context=ssl._create_unverified_context()
        )
        try:
            connection.putrequest("POST", "/", skip_accept_encoding=True)
            connection.putheader("Accept", "application/json")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(payload)))
            connection.endheaders()
            connection.send(payload)
            response = connection.getresponse()
            raw = response.read(2_000_001)
            if response.status != 200 or len(raw) > 2_000_000:
                raise RuntimeError("Invalid IP Control response")
            reply = json.loads(raw)
            if "error" in reply or "code" in reply or not isinstance(reply.get("result"), dict):
                raise RuntimeError("TV rejected IP Control request")
            return reply["result"]
        finally:
            connection.close()

    def pair(self):
        result = self.request("createAccessToken", pairing=True)
        token = result.get("AccessToken")
        if not isinstance(token, str) or not token:
            raise RuntimeError("No pairing token returned")
        atomic_json(self.token_file, {"token": token, "host": self.host})

    def power(self):
        return self.request("powerControl").get("power", "unknown")

    def standby(self):
        return self.request("powerControl", {"power": "powerOff"}).get("power", "unknown")

    def power_on(self):
        return self.request("powerControl", {"power": "powerOn"}).get("power", "unknown")


def wake(mac, broadcast="255.255.255.255"):
    """Send one magic packet at an explicit, scheduled wake boundary."""
    if not isinstance(mac, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac):
        raise ValueError("A valid TV MAC address is required")
    address = bytes.fromhex(mac.replace(":", ""))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(b"\xff" * 6 + address * 16, (broadcast, 9))
