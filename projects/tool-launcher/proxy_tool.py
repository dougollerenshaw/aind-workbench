"""Forward `/session_tracker/...` to the session tracker's own server.

The tracker (github.com/AllenNeuralDynamics/session_tracker_prototype) is a separate uv
project with its own process, so the launcher does not import it; it forwards requests to
it over localhost and hands the answers back unchanged. The tracker's page works behind a
path prefix as long as the prefix is stripped (DispatcherMiddleware does that) and the bare
prefix redirects to the trailing-slash form (done here).

Start the tracker next to the launcher:  cd session_tracker_prototype && uv run tracker --port 8765
Override the address with SESSION_TRACKER_URL.
"""

import http.client
import os
import urllib.error
import urllib.request
from urllib.parse import quote

TRACKER_URL = os.environ.get("SESSION_TRACKER_URL", "http://127.0.0.1:8765").rstrip("/")
TIMEOUT_S = 180  # the tracker's on-demand log fetches can take a while
_HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
               "proxy-authenticate", "proxy-authorization", "content-length"}


def session_tracker_app(environ, start_response):
    """WSGI app: relay one request to the tracker and return its response."""
    path = environ.get("PATH_INFO") or ""
    query = environ.get("QUERY_STRING") or ""
    if path == "":  # bare /session_tracker: relative URLs on the page need the trailing slash
        location = environ.get("SCRIPT_NAME", "") + "/" + (f"?{query}" if query else "")
        start_response("301 Moved Permanently", [("Location", location), ("Content-Length", "0")])
        return [b""]
    method = environ.get("REQUEST_METHOD", "GET")
    body = None
    if method in ("POST", "PUT", "PATCH"):
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        body = environ["wsgi.input"].read(length) if length else b""
    headers = {"Accept": environ.get("HTTP_ACCEPT", "*/*"), "Accept-Encoding": "identity"}
    if environ.get("CONTENT_TYPE"):
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    url = TRACKER_URL + quote(path) + (f"?{query}" if query else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=TIMEOUT_S) as resp:
            status, data, upstream = resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as err:  # the tracker's own 4xx/5xx answers pass through
        status, data, upstream = err.code, err.read(), err.headers
    except (urllib.error.URLError, OSError, http.client.HTTPException) as err:
        text = (f"The session tracker is not answering at {TRACKER_URL} ({getattr(err, 'reason', err)}).\n"
                "On the VM: cd session_tracker_prototype && uv run tracker --port 8765\n").encode()
        start_response("502 Bad Gateway", [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(text)))])
        return [text]
    out = [(k, v) for k, v in upstream.items() if k.lower() not in _HOP_BY_HOP]
    out.append(("Content-Length", str(len(data))))
    start_response(f"{status} {http.client.responses.get(status, '')}".strip(), out)
    return [data]
