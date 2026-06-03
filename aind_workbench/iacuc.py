"""IACUC / ethics-review protocol lookup for a mouse.

Public function: ``get_iacuc_id_for_mouse(subject_id)`` -> current protocol number
(e.g. ``"2414"``), or ``None``. With ``return_details=True`` it returns::

    {"subject_id": "762287", "ethics_review_id": "2414", "source": "docdb",
     "history": [ {start_date, ethics_review_id}, ... ]}

Two-stage lookup:
  1. FAST — AIND DocDB (``metadata_index.data_assets``, v2 API). Public read, no creds.
  2. FALLBACK — ``aind-metadata-service`` ``GET /api/v2/procedures/{subject_id}`` when
     DocDB has no protocol for the subject (slow ~30 s; needs the internal host).

The protocol lives on each surgery as a bare number string. The field name depends on
the aind-data-schema generation: v1 used ``iacuc_protocol``; v2 (queried here) renamed
it to ``ethics_review_id``. Both are read. Sentinels like ``"unknown"`` are ignored.
For a mouse that changed protocols, the most recent surgery (by ``start_date``) wins.
(This is the LabTracks form; Dataverse uses ``"2414-Westlake"``.)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger("aind_workbench.iacuc")

DOCDB_HOST = "api.allenneuraldynamics.org"
DOCDB_API_VERSION = "v2"
DOCDB_DB = "metadata_index"
DOCDB_COLLECTION = "data_assets"
METADATA_SERVICE_HOST = "https://aind-metadata-service"

# Surgery protocol fields, oldest schema name first. v1 -> iacuc_protocol;
# v2 -> ethics_review_id (renamed). We read both.
_PROTOCOL_KEYS = ("iacuc_protocol", "ethics_review_id")

# Sentinel strings that appear in the data but are not real protocol numbers.
_NON_PROTOCOL_VALUES = {"", "unknown", "none", "n/a", "na", "null", "tbd"}

# (surgery start_date, protocol number)
SurgeryProtocol = Tuple[Optional[str], str]


def _protocol_value(surgery: dict) -> Optional[str]:
    """Return a real protocol number from a surgery dict, or None (sentinels skipped)."""
    for key in _PROTOCOL_KEYS:
        value = surgery.get(key)
        if isinstance(value, str) and value.strip().lower() not in _NON_PROTOCOL_VALUES:
            return value.strip()
    return None


def _walk_surgeries(obj) -> List[SurgeryProtocol]:
    """Recursively collect (start_date, protocol) from any nested surgery dicts.

    Robust to the DocDB record shape and to the metadata-service envelope (which may
    wrap the model in a ``data`` field).
    """
    found: List[SurgeryProtocol] = []
    if isinstance(obj, dict):
        protocol = _protocol_value(obj)
        if protocol:
            found.append((obj.get("start_date"), protocol))
        for value in obj.values():
            found.extend(_walk_surgeries(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_walk_surgeries(value))
    return found


def _pick_current(pairs: List[SurgeryProtocol]) -> Optional[str]:
    """Protocol from the most recent surgery (by start_date)."""
    pairs = [(d, p) for d, p in pairs if p]
    if not pairs:
        return None
    distinct = sorted({p for _, p in pairs})
    if len(distinct) > 1:
        logger.warning(
            "subject has multiple IACUC protocols across surgeries: %s "
            "(returning the most recent by start_date)",
            distinct,
        )
    # ISO date strings sort lexicographically; a missing date sorts oldest.
    pairs.sort(key=lambda dp: (dp[0] is not None, dp[0] or ""), reverse=True)
    return pairs[0][1]


# ── stage 1: DocDB (fast) ──────────────────────────────────────────────────────
def _from_docdb(subject_id, host: str = DOCDB_HOST, timeout: int = 20) -> List[SurgeryProtocol]:
    """Surgery protocols for a subject from the DocDB metadata index."""
    url = f"https://{host}/{DOCDB_API_VERSION}/{DOCDB_DB}/{DOCDB_COLLECTION}/find"
    params = {
        "filter": json.dumps(
            {"subject.subject_id": str(subject_id), "procedures": {"$ne": None}}
        ),
        "projection": json.dumps(
            {
                "procedures.subject_procedures.start_date": 1,
                "procedures.subject_procedures.iacuc_protocol": 1,  # v1 field
                "procedures.subject_procedures.ethics_review_id": 1,  # v2 field
            }
        ),
        "limit": "0",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return _walk_surgeries(resp.json())


# ── stage 2: metadata service (slow fallback) ──────────────────────────────────
def _from_metadata_service(
    subject_id, host: str = METADATA_SERVICE_HOST, timeout: int = 90
) -> List[SurgeryProtocol]:
    """Surgery protocols from the metadata-service procedures endpoint."""
    url = f"{host.rstrip('/')}/api/v2/procedures/{subject_id}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return _walk_surgeries(resp.json())


# ── public API ─────────────────────────────────────────────────────────────────
def get_iacuc_id_for_mouse(
    subject_id,
    *,
    docdb_host: str = DOCDB_HOST,
    metadata_service_host: str = METADATA_SERVICE_HOST,
    allow_fallback: bool = True,
    return_details: bool = False,
):
    """Return the current protocol number for *subject_id* (bare string), or None.

    With ``return_details=True`` returns ``{subject_id, ethics_review_id, source,
    history}``.
    """
    try:
        pairs = _from_docdb(subject_id, host=docdb_host)
    except requests.RequestException as exc:
        logger.warning("DocDB lookup failed for %s: %s", subject_id, exc)
        pairs = []
    source = "docdb" if pairs else None

    if not pairs and allow_fallback:
        logger.info(
            "No protocol in DocDB for %s; falling back to metadata service…",
            subject_id,
        )
        try:
            pairs = _from_metadata_service(subject_id, host=metadata_service_host)
            source = "metadata_service" if pairs else None
        except requests.RequestException as exc:
            logger.warning("Metadata-service fallback failed for %s: %s", subject_id, exc)

    protocol = _pick_current(pairs)

    if return_details:
        history = sorted(
            {(d, p) for d, p in pairs if p},
            key=lambda dp: dp[0] or "",
            reverse=True,
        )
        # Insertion order matters for presentation: subject_id, ethics_review_id, source.
        return {
            "subject_id": str(subject_id),
            "ethics_review_id": protocol,
            "source": source if protocol else None,
            "history": [
                {"start_date": d, "ethics_review_id": p} for d, p in history
            ],
        }
    return protocol


# Backwards-compatible alias (earlier name).
get_iacuc_protocol = get_iacuc_id_for_mouse


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Get the current IACUC/ethics-review protocol number for a mouse."
    )
    parser.add_argument("subject_id", help="Mouse / subject ID, e.g. 762287")
    parser.add_argument(
        "--details", action="store_true",
        help="Print the full JSON (ethics_review_id + source + per-surgery history).",
    )
    parser.add_argument(
        "--no-fallback", action="store_true",
        help="DocDB only; skip the slow metadata-service fallback.",
    )
    parser.add_argument("--docdb-host", default=DOCDB_HOST)
    parser.add_argument("--metadata-service-host", default=METADATA_SERVICE_HOST)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = get_iacuc_id_for_mouse(
        args.subject_id,
        docdb_host=args.docdb_host,
        metadata_service_host=args.metadata_service_host,
        allow_fallback=not args.no_fallback,
        return_details=args.details,
    )
    if args.details:
        print(json.dumps(result, indent=2))
        found = result.get("ethics_review_id")
    else:
        print(result if result is not None else "")
        found = result
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(_main())
