"""IACUC-protocol lookup: a small web form + REST endpoint.

Mounted by the tool-launcher at ``/iacuc_lookup``.

- A browser visiting ``/iacuc_lookup`` gets an HTML page with a single subject-id
  field and a "Get IACUC ID" button. Submitting navigates to
  ``/iacuc_lookup?subject_id=<id>`` and shows the result on the same page.
- Programmatic callers get JSON ``{subject_id: protocol}``: anything that doesn't
  accept HTML (e.g. ``curl``), or any request with ``?format=json``.

Accepted request forms:
    /iacuc_lookup                     -> empty form
    /iacuc_lookup?subject_id=762287   -> result (HTML for browsers, JSON otherwise)
    /iacuc_lookup/762287              -> same, via path
    /iacuc_lookup?...&details=true    -> JSON with source + per-surgery history
    /iacuc_lookup?...&fallback=false  -> DocDB only; skip the slow fallback
"""
import sys
from pathlib import Path

# Make the repo-root `aind_workbench` package importable even without `pip install`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from flask import Flask, jsonify, request  # noqa: E402
from markupsafe import escape  # noqa: E402

from aind_workbench import get_iacuc_id_for_mouse  # noqa: E402

app = Flask(__name__)


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

# Absolute path the form submits to (matches the tool-launcher mount point).
_FORM_ACTION = "/iacuc_lookup"


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


def _wants_json():
    """JSON for explicit ?format=json, or for clients that don't accept HTML."""
    if request.args.get("format", "").lower() == "json":
        return True
    return "text/html" not in request.headers.get("Accept", "")


def _render_page(subject_id, details=None, status=200):
    """Render the form page, optionally with a lookup result."""
    sid = escape(subject_id or "")
    result_html = ""
    if details is not None:
        protocol = details.get("iacuc_protocol")
        source = details.get("source")
        history = details.get("history") or []
        if protocol:
            answer = (
                f'<div class="protocol">{escape(protocol)}</div>'
                f'<div class="muted">source: {escape(source or "n/a")}</div>'
            )
        else:
            answer = (
                '<div class="protocol none">— no IACUC protocol found —</div>'
                '<div class="muted">not in DocDB; the metadata-service fallback '
                "may be unreachable from here, or none is recorded.</div>"
            )
        history_html = ""
        if len(history) > 1:
            rows = "".join(
                f"<tr><td>{escape(h.get('start_date') or '')}</td>"
                f"<td>{escape(h.get('iacuc_protocol') or '')}</td></tr>"
                for h in history
            )
            history_html = (
                '<div class="muted" style="margin-top:.75rem">multiple protocols '
                "across surgeries (most recent shown above):</div>"
                "<table><tr><th>start date</th><th>protocol</th></tr>"
                f"{rows}</table>"
            )
        result_html = (
            f'<div class="result"><div>Subject <b>{sid}</b>:</div>'
            f"{answer}{history_html}"
            f'<div class="muted" style="margin-top:.75rem">'
            f'<a href="{_FORM_ACTION}?subject_id={sid}&amp;format=json">raw JSON</a>'
            "</div></div>"
        )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>IACUC Lookup</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 640px;
         margin: 3rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  form {{ display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }}
  input {{ font-size: 1rem; padding: .45rem .55rem; }}
  button {{ font-size: 1rem; padding: .45rem .9rem; cursor: pointer; }}
  .result {{ margin-top: 1.5rem; padding: 1rem 1.25rem; border: 1px solid #ddd;
             border-radius: 10px; background: #fafafa; }}
  .protocol {{ font-size: 1.8rem; font-weight: 700; margin: .25rem 0; }}
  .protocol.none {{ font-size: 1.1rem; font-weight: 600; color: #a00; }}
  .muted {{ color: #666; font-size: .9rem; }}
  table {{ border-collapse: collapse; margin-top: .4rem; }}
  td, th {{ border: 1px solid #ddd; padding: .25rem .6rem; font-size: .9rem;
            text-align: left; }}
</style></head><body>
  <h1>IACUC Protocol Lookup</h1>
  <form method="get" action="{_FORM_ACTION}">
    <label>Subject ID:
      <input name="subject_id" value="{sid}" placeholder="e.g. 762287" autofocus>
    </label>
    <button type="submit">Get IACUC ID</button>
  </form>
  {result_html}
</body></html>"""
    return html, status


@app.route("/")
@app.route("/<subject_id>")
def iacuc_lookup(subject_id=None):
    """Form page (browser) or JSON ``{subject_id: protocol}`` (API)."""
    sid = subject_id or _resolve_subject_id()
    json_mode = _wants_json()
    details = _truthy(request.args.get("details"))
    allow_fallback = _truthy(request.args.get("fallback"), default=True)

    # No subject id yet: show the empty form (browser) or a 400 (API).
    if not sid:
        if json_mode:
            return (
                jsonify(
                    {
                        "error": "provide a subject_id, "
                        "e.g. /iacuc_lookup?subject_id=762287"
                    }
                ),
                400,
            )
        return _render_page(subject_id=None)

    try:
        info = get_iacuc_id_for_mouse(
            sid, allow_fallback=allow_fallback, return_details=True
        )
    except Exception as exc:  # surface as 502 rather than a 500 stack trace
        app.logger.exception("IACUC lookup failed for %s", sid)
        if json_mode:
            return jsonify({"error": str(exc), "subject_id": sid}), 502
        return _render_page(subject_id=sid, details={"iacuc_protocol": None})

    if json_mode:
        if details:
            return jsonify(info)
        return jsonify({sid: info.get("iacuc_protocol")})  # {subject_id: protocol}
    return _render_page(subject_id=sid, details=info)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IACUC lookup web app (standalone)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=True)
