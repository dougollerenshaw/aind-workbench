"""IACUC / ethics-review protocol lookup for a mouse.

Public function: ``get_iacuc_id_for_mouse(subject_id)`` -> current protocol number
(e.g. ``"2414"``), or ``None``. With ``return_details=True`` it returns a blob::

    {
      "subject_id":      "762287",
      "ethics_review_id": "2414",         # the protocol number (None if not found)
      "source":          "docdb",          # "docdb" | "metadata_service" | None
      "date_queried":    "2026-05-07T09:10:57.441Z",
      "history":         [ {start_date, ethics_review_id}, ... ]
    }

``date_queried`` is provenance for catching stale IDs:
  - source == "docdb": the ``_created`` timestamp of the DocDB procedures record the
    value came from (the freshest record asserting that protocol).
  - source == "metadata_service": the current UTC time, since that path queries live.

Two-stage lookup:
  1. FAST — AIND DocDB (``metadata_index.data_assets``, v2 API). Public read, no creds.
  2. FALLBACK — ``aind-metadata-service`` ``GET /api/v2/procedures/{subject_id}`` when
     DocDB has no protocol for the subject (slow ~30 s; needs the internal host).

The protocol lives on each surgery as a bare number string. The field name depends on
the aind-data-schema generation: v1 used ``iacuc_protocol``; v2 (queried here) renamed
it to ``ethics_review_id``. Both are read. Sentinels like ``"unknown"`` are ignored.
(This is the LabTracks form; Dataverse uses ``"2414-Westlake"``.)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
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

# (surgery start_date, protocol number, docdb record _created)  -- _created is None
# for the metadata-service path.
SurgeryHit = Tuple[Optional[str], str, Optional[str]]


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 'Z' string, matching DocDB's format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _protocol_value(surgery: dict) -> Optional[str]:
    """Return a real protocol number from a surgery dict, or None (sentinels skipped)."""
    for key in _PROTOCOL_KEYS:
        value = surgery.get(key)
        if isinstance(value, str) and value.strip().lower() not in _NON_PROTOCOL_VALUES:
            return value.strip()
    return None


def _walk_surgeries(obj) -> List[Tuple[Optional[str], str]]:
    """Recursively collect (start_date, protocol) from any nested surgery dicts.

    Used for the metadata-service response, whose envelope may wrap the model in a
    ``data`` field.
    """
    found: List[Tuple[Optional[str], str]] = []
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


# ── stage 1: DocDB (fast) ──────────────────────────────────────────────────────
def _from_docdb(subject_id, host: str = DOCDB_HOST, timeout: int = 20) -> List[SurgeryHit]:
    """Surgery protocols + the record's ``_created`` date, from the DocDB index."""
    url = f"https://{host}/{DOCDB_API_VERSION}/{DOCDB_DB}/{DOCDB_COLLECTION}/find"
    params = {
        "filter": json.dumps(
            {"subject.subject_id": str(subject_id), "procedures": {"$ne": None}}
        ),
        "projection": json.dumps(
            {
                "_created": 1,  # docdb record creation date -> date_queried
                "procedures.subject_procedures.start_date": 1,
                "procedures.subject_procedures.iacuc_protocol": 1,  # v1 field
                "procedures.subject_procedures.ethics_review_id": 1,  # v2 field
            }
        ),
        "limit": "0",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    hits: List[SurgeryHit] = []
    for record in resp.json():
        created = (record or {}).get("_created")
        procedures = (record or {}).get("procedures") or {}
        for surgery in procedures.get("subject_procedures") or []:
            protocol = _protocol_value(surgery)
            if protocol:
                hits.append((surgery.get("start_date"), protocol, created))
    return hits


# ── stage 2: metadata service (slow fallback) ──────────────────────────────────
def _from_metadata_service(
    subject_id, host: str = METADATA_SERVICE_HOST, timeout: int = 90
) -> List[SurgeryHit]:
    """Surgery protocols from the metadata-service procedures endpoint (no record date)."""
    url = f"{host.rstrip('/')}/api/v2/procedures/{subject_id}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return [(start, protocol, None) for start, protocol in _walk_surgeries(resp.json())]


# ── selection ──────────────────────────────────────────────────────────────────
def _resolve(hits: List[SurgeryHit], source: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Pick the most recent surgery's protocol and compute ``date_queried``."""
    hits = [h for h in hits if h[1]]
    if not hits:
        return None, None
    distinct = sorted({p for _, p, _ in hits})
    if len(distinct) > 1:
        logger.warning(
            "subject has multiple IACUC protocols across surgeries: %s "
            "(returning the most recent by start_date)",
            distinct,
        )
    # ISO date strings sort lexicographically; a missing date sorts oldest.
    hits.sort(key=lambda h: (h[0] is not None, h[0] or ""), reverse=True)
    protocol = hits[0][1]

    if source == "metadata_service":
        return protocol, _now_iso()
    # docdb: freshest record _created among records that assert this protocol.
    createds = [c for _, p, c in hits if p == protocol and c]
    return protocol, (max(createds) if createds else None)


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

    With ``return_details=True`` returns the provenance blob documented in the module
    docstring (``subject_id``, ``ethics_review_id``, ``source``, ``date_queried``,
    ``history``).
    """
    try:
        hits = _from_docdb(subject_id, host=docdb_host)
    except requests.RequestException as exc:
        logger.warning("DocDB lookup failed for %s: %s", subject_id, exc)
        hits = []
    source = "docdb" if hits else None

    if not hits and allow_fallback:
        logger.info(
            "No protocol in DocDB for %s; falling back to metadata service…",
            subject_id,
        )
        try:
            hits = _from_metadata_service(subject_id, host=metadata_service_host)
            source = "metadata_service" if hits else None
        except requests.RequestException as exc:
            logger.warning("Metadata-service fallback failed for %s: %s", subject_id, exc)

    protocol, date_queried = _resolve(hits, source)

    if return_details:
        history = sorted(
            {(d, p) for d, p, _ in hits if p},
            key=lambda dp: dp[0] or "",
            reverse=True,
        )
        return {
            "subject_id": str(subject_id),
            "ethics_review_id": protocol,
            "source": source if protocol else None,
            "date_queried": date_queried,
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
        help="Print the full JSON blob (ethics_review_id + source + date_queried + history).",
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
