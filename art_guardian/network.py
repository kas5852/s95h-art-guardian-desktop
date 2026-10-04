"""Small HTTP client: no automatic POST retries, redirects, or ambient proxy credentials."""

import json
import ssl
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("HTTP redirect refused")


def request_json(url, *, token=None, payload=None, timeout=8, local_self_signed=False):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    handlers = [ProxyHandler({}), NoRedirect()]
    if local_self_signed:
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    opener = build_opener(*handlers)
    try:
        with opener.open(Request(url, data=data, headers=headers), timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("Response exceeds size limit")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        # Never include request headers, token, response body, or user URL in an error.
        raise RuntimeError(f"HTTP {exc.code}") from None
