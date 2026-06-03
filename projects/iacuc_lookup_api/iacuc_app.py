"""IACUC-protocol lookup: a JSON REST endpoint with a small form entry page.

Mounted by the tool-launcher at ``/iacuc_lookup``.

- ``/iacuc_lookup?subject_id=762287`` -> **always JSON** (easy to hit
  programmatically; same response in a browser or via ``curl``)::

      {"subject_id": "762287", "ethics_review_id": "2414",
       "source": "docdb", "date_queried": "2026-05-07T09:10:57.441Z"}

- ``/iacuc_lookup`` with no subject id -> an HTML page with a single field and a
  "Get IACUC ID" button that GET-submits to the JSON URL above.

Accepted request forms:
    /iacuc_lookup?subject_id=762287                 -> the blob above
    /iacuc_lookup/762287                            -> same
    /iacuc_lookup?subject_id=762287&details=true    -> blob + per-surgery history
    /iacuc_lookup?subject_id=762287&fallback=false  -> DocDB only; skip the slow fallback
"""
import sys
from pathlib import Path

# Make the repo-root `aind_workbench` package importable even without `pip install`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from flask import Flask, jsonify, request  # noqa: E402

from aind_workbench import get_iacuc_id_for_mouse  # noqa: E402

app = Flask(__name__)

# Absolute path the form submits to (matches the tool-launcher mount point).
_FORM_ACTION = "/iacuc_lookup"


class _RootSlashFix:
    """Treat the bare mount path (``/iacuc_lookup``) as ``/`` without a 308 redirect.

    Under DispatcherMiddleware the mount root arrives with an empty PATH_INFO, which
    Flask would otherwise redirect to a trailing slash. Normalizing here keeps the
    clean ``/iacuc_lookup?subject_id=...`` URL the form posts to.
    """

    def __init__(self, wsgi_app):
        self._wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO", "") == "":
            environ["PATH_INFO"] = "/"
        return self._wsgi_app(environ, start_response)


app.wsgi_app = _RootSlashFix(app.wsgi_app)

# Static entry form (no user input is reflected back, so no escaping needed).
_FORM_PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>IACUC Lookup</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 640px;
         margin: 3rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  form {{ display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }}
  input {{ font-size: 1rem; padding: .45rem .55rem; }}
  button {{ font-size: 1rem; padding: .45rem .9rem; cursor: pointer; }}
  .muted {{ color: #666; font-size: .9rem; margin-top: 1rem; }}
  code {{ background: #f2f2f2; padding: .1rem .3rem; border-radius: 4px; }}
</style></head><body>
  <h1>IACUC Protocol Lookup</h1>
  <form method="get" action="{_FORM_ACTION}">
    <label>Subject ID:
      <input name="subject_id" placeholder="e.g. 762287" autofocus>
    </label>
    <button type="submit">Get IACUC ID</button>
  </form>
  <p class="muted">Returns JSON, e.g.
     <code>{{"subject_id": "762287", "ethics_review_id": "2414", "source": "docdb",
     "date_queried": "2026-05-07T09:10:57.441Z"}}</code>.
     Add <code>&amp;details=true</code> for per-surgery history.</p>
</body></html>"""


def _resolve_subject_id():
    """Pull the subject id from ?subject_id=, or a bare ?<id> query string."""
    sid = request.args.get("subject_id")
    if sid:
        return sid.strip()
    qs = request.query_string.decode().strip()
    if qs and "=" not in qs and "&" not in qs:
        return qs
    return None


def _truthy(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y")


@app.route("/")
@app.route("/<subject_id>")
def iacuc_lookup(subject_id=None):
    """JSON blob (subject_id, ethics_review_id, source, date_queried) when given an
    id; else the HTML entry form."""
    sid = subject_id or _resolve_subject_id()

    # No subject id -> show the form (the entry page). Programmatic callers always
    # pass a subject_id and so always get JSON below.
    if not sid:
        return _FORM_PAGE

    details = _truthy(request.args.get("details"))
    allow_fallback = _truthy(request.args.get("fallback"), default=True)
    try:
        info = get_iacuc_id_for_mouse(
            sid, allow_fallback=allow_fallback, return_details=True
        )
    except Exception as exc:  # surface as 502 rather than a 500 stack trace
        app.logger.exception("IACUC lookup failed for %s", sid)
        return jsonify({"error": str(exc), "subject_id": sid}), 502

    if details:
        return jsonify(info)  # adds per-surgery history
    # Default blob: subject_id, ethics_review_id, source, date_queried
    return jsonify(
        {k: info[k] for k in ("subject_id", "ethics_review_id", "source", "date_queried")}
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IACUC lookup web app (standalone)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=True)
