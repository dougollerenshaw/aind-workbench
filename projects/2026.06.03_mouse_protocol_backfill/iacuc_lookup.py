# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31"]
# ///
"""IACUC / ethics-review protocol lookup for a mouse (self-contained).

A standalone copy of the two-stage DocDB -> metadata-service lookup, kept inside this
backfill folder on purpose: it must NOT import from the repo's ``aind_workbench``
package, so the whole folder ports cleanly into a PR on
``AllenNeuralDynamics/aind-dataverse-migration-scripts`` without external deps.

``get_iacuc_id_for_mouse(subject_id)`` -> current protocol number (e.g. ``"2414"``)
or ``None``.

  1. FAST — AIND DocDB (``metadata_index.data_assets``, v2 API). Public read, no creds.
  2. FALLBACK — ``aind-metadata-service`` ``/api/v2/procedures/{subject_id}`` when DocDB
     has no protocol (slow ~30 s; needs the internal host / VPN).

The protocol is on each surgery as a bare number string. The field name depends on the
aind-data-schema generation: v1 ``iacuc_protocol``; v2 (queried here) ``ethics_review_id``.
Both are read; sentinels like ``"unknown"`` are ignored; for a mouse that changed
protocols the most recent surgery (by ``start_date``) wins.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger("iacuc_lookup")

DOCDB_HOST = "api.allenneuraldynamics.org"
DOCDB_API_VERSION = "v2"
DOCDB_DB = "metadata_index"
DOCDB_COLLECTION = "data_assets"
METADATA_SERVICE_HOST = "https://aind-metadata-service"

_PROTOCOL_KEYS = ("iacuc_protocol", "ethics_review_id")  # v1, v2 field names
_NON_PROTOCOL_VALUES = {"", "unknown", "none", "n/a", "na", "null", "tbd"}

SurgeryProtocol = Tuple[Optional[str], str]  # (start_date, protocol number)


def _protocol_value(surgery: dict) -> Optional[str]:
    """Return a real protocol number from a surgery dict, or None (sentinels skipped)."""
    for key in _PROTOCOL_KEYS:
        value = surgery.get(key)
        if isinstance(value, str) and value.strip().lower() not in _NON_PROTOCOL_VALUES:
            return value.strip()
    return None


def _walk_surgeries(obj) -> List[SurgeryProtocol]:
    """Recursively collect (start_date, protocol) from any nested surgery dicts."""
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
    pairs.sort(key=lambda dp: (dp[0] is not None, dp[0] or ""), reverse=True)
    return pairs[0][1]


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
                "procedures.subject_procedures.iacuc_protocol": 1,
                "procedures.subject_procedures.ethics_review_id": 1,
            }
        ),
        "limit": "0",
    }
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return _walk_surgeries(resp.json())


def _from_metadata_service(
    subject_id, host: str = METADATA_SERVICE_HOST, timeout: int = 90
) -> List[SurgeryProtocol]:
    """Surgery protocols from the metadata-service procedures endpoint."""
    url = f"{host.rstrip('/')}/api/v2/procedures/{subject_id}"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return _walk_surgeries(resp.json())


def get_iacuc_id_for_mouse(
    subject_id,
    *,
    docdb_host: str = DOCDB_HOST,
    metadata_service_host: str = METADATA_SERVICE_HOST,
    allow_fallback: bool = True,
    return_details: bool = False,
):
    """Return the current protocol number for *subject_id* (bare string) or None.

    With ``return_details=True`` returns ``{subject_id, ethics_review_id, source}``.
    """
    try:
        pairs = _from_docdb(subject_id, host=docdb_host)
    except requests.RequestException as exc:
        logger.warning("DocDB lookup failed for %s: %s", subject_id, exc)
        pairs = []
    source = "docdb" if pairs else None

    if not pairs and allow_fallback:
        try:
            pairs = _from_metadata_service(subject_id, host=metadata_service_host)
            source = "metadata_service" if pairs else None
        except requests.RequestException as exc:
            logger.warning("Metadata-service fallback failed for %s: %s", subject_id, exc)

    protocol = _pick_current(pairs)
    if return_details:
        return {
            "subject_id": str(subject_id),
            "ethics_review_id": protocol,
            "source": source if protocol else None,
        }
    return protocol


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for arg in sys.argv[1:]:
        print(arg, "->", get_iacuc_id_for_mouse(arg))
