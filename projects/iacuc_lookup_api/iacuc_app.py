"""Tiny REST API exposing the IACUC-protocol lookup.

Mounted by the tool-launcher at ``/iacuc_lookup``. Returns ``{subject_id: protocol}``.

Accepted request forms (all equivalent):
    /iacuc_lookup?subject_id=762287
    /iacuc_lookup/762287
    /iacuc_lookup?762287              (bare query string)

Optional query params:
    details=true     -> return the richer blob (protocol + source + history)
    fallback=false   -> DocDB only; skip the slow metadata-service fallback
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
    """Return the current IACUC protocol for a mouse as JSON."""
    sid = subject_id or _resolve_subject_id()
    if not sid:
        return (
            jsonify(
                {
                    "error": "provide a subject_id, "
                    "e.g. /iacuc_lookup?subject_id=762287 or /iacuc_lookup/762287"
                }
            ),
            400,
        )

    details = _truthy(request.args.get("details"))
    allow_fallback = _truthy(request.args.get("fallback"), default=True)

    try:
        result = get_iacuc_id_for_mouse(
            sid, allow_fallback=allow_fallback, return_details=details
        )
    except Exception as exc:  # surface as 502 rather than a 500 stack trace
        app.logger.exception("IACUC lookup failed for %s", sid)
        return jsonify({"error": str(exc), "subject_id": sid}), 502

    if details:
        return jsonify(result)
    # Requested shape: {subject_id: protocol_id}
    return jsonify({sid: result})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="IACUC lookup REST API (standalone)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=True)
