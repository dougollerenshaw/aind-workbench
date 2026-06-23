# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests>=2.31",
#   "msal>=1.28",
#   "python-dotenv>=1.0",
# ]
# ///
"""
Backfill ``aibs_dim_mice.aibs_iacuc_protocol`` in Dataverse.

Each mouse's protocol is sourced from the AIND metadata pipeline (DocDB fast path,
metadata-service fallback) via the sibling ``iacuc_lookup`` module — i.e. the same
logic the standalone lookup tool uses. This is a ONE-TIME backfill of historical data;
going forward the source of truth is Dataverse itself (maintained by LAS / behavior /
neurosurgery).

Flow:
  1. Auth to Dataverse (MSAL username/password).
  2. Fetch mice from ``aibs_dim_mices`` (default: those whose ``aibs_iacuc_protocol``
     lookup is empty — the actual backfill target).
  3. Build {numeric protocol key -> ``aibs_dim_iacuc_protocolsid`` GUID} from
     ``aibs_dim_iacuc_protocolses``. Dataverse stores ``"2414-Westlake"`` while the
     lookup yields the bare ``"2414"``, so we match on the leading digits.
  4. For each mouse: look up its protocol number, map it to the Dataverse protocol GUID.
  5. PATCH ``aibs_dim_mices(<guid>)`` binding ``aibs_iacuc_protocol@odata.bind``.

SAFETY — writes are off unless you ask twice:
  * Dry-run is the default. Writing requires the ``--apply`` flag, AND
  * the env var ``IACUC_BACKFILL_CONFIRM_WRITE=1`` must be set. Without both, the write
    function raises. A bare ``--apply`` (or any accidental call) cannot write.

Usage:
    # Read-only dry run (no creds needed for the offline bits; reads for the plan):
    uv run backfill_iacuc_protocol.py --top 10
    uv run backfill_iacuc_protocol.py                     # full dry run (all empty-protocol mice)

    # Real write (only after the migration-repo PR is approved):
    IACUC_BACKFILL_CONFIRM_WRITE=1 uv run backfill_iacuc_protocol.py --apply

Required env (a .env in this dir / repo root is auto-loaded):
    DATAVERSE_CLIENT_ID, DATAVERSE_TENANT_ID, DATAVERSE_HOST,
    DATAVERSE_USERNAME, DATAVERSE_PASSWORD
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests

from iacuc_lookup import get_iacuc_id_for_mouse  # sibling module (NOT aind_workbench)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


# ── Dataverse schema constants ────────────────────────────────────────────────
API_VERSION = "v9.2"
MICE_ENTITY_SET = "aibs_dim_mices"
MICE_ID_FIELD = "aibs_mouse_id"
MICE_GUID_FIELD = "aibs_dim_miceid"
IACUC_PROTOCOL_VALUE_FIELD = "_aibs_iacuc_protocol_value"  # the lookup's stored value

IACUC_ENTITY_SET = "aibs_dim_iacuc_protocolses"
IACUC_ID_FIELD = "aibs_protocol_id"
IACUC_GUID_FIELD = "aibs_dim_iacuc_protocolsid"

# Navigation property for @odata.bind. Matches the lookup whose value field is
# _aibs_iacuc_protocol_value. VERIFY once against {host}/api/data/v9.2/$metadata.
IACUC_PROTOCOL_NAV = "aibs_iacuc_protocol"

REQUIRED_ENV = [
    "DATAVERSE_CLIENT_ID",
    "DATAVERSE_TENANT_ID",
    "DATAVERSE_HOST",
    "DATAVERSE_USERNAME",
    "DATAVERSE_PASSWORD",
]

# Second gate (in addition to --apply) that must be set to permit any write.
WRITE_CONFIRM_ENV = "IACUC_BACKFILL_CONFIRM_WRITE"

logger = logging.getLogger("iacuc_backfill")


# ── auth + http (reads) ─────────────────────────────────────────────────────────
def get_access_token() -> str:
    """Acquire a Dataverse token via the MSAL username/password flow."""
    import msal

    missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    host = os.getenv("DATAVERSE_HOST", "").rstrip("/")
    app = msal.PublicClientApplication(
        client_id=os.getenv("DATAVERSE_CLIENT_ID"),
        authority=f"https://login.microsoftonline.com/{os.getenv('DATAVERSE_TENANT_ID')}",
    )
    logger.info("Acquiring Dataverse access token …")
    result = app.acquire_token_by_username_password(
        username=os.getenv("DATAVERSE_USERNAME"),
        password=os.getenv("DATAVERSE_PASSWORD"),
        scopes=[f"{host}/user_impersonation"],
    )
    if "access_token" not in result:
        raise RuntimeError(
            f"Failed to acquire access token: {result.get('error_description', 'Unknown error')}"
        )
    return result["access_token"]


def make_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    return session


def _api_base() -> str:
    return f"{os.getenv('DATAVERSE_HOST', '').rstrip('/')}/api/data/{API_VERSION}"


def query_dataverse(
    session: requests.Session, entity_set: str, *, select: str, filter_str: Optional[str] = None
) -> List[Dict]:
    """GET rows from an entity set, following @odata.nextLink paging. Read-only."""
    params: Dict[str, str] = {"$select": select}
    if filter_str:
        params["$filter"] = filter_str
    url: Optional[str] = f"{_api_base()}/{entity_set}"
    out: List[Dict] = []
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        out.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
        params = {}
    return out


# ── the only write in the file — double-gated ────────────────────────────────────
def patch_mouse_protocol(
    session: requests.Session, mouse_guid: str, protocol_guid: str
) -> requests.Response:
    """Bind the IACUC protocol lookup on one mouse. Refuses unless explicitly confirmed."""
    if os.getenv(WRITE_CONFIRM_ENV) != "1":
        raise RuntimeError(
            f"Refusing to write: set {WRITE_CONFIRM_ENV}=1 (in addition to --apply) to "
            "enable Dataverse writes. This guard makes dry runs incapable of writing."
        )
    url = f"{_api_base()}/{MICE_ENTITY_SET}({mouse_guid})"
    body = {f"{IACUC_PROTOCOL_NAV}@odata.bind": f"/{IACUC_ENTITY_SET}({protocol_guid})"}
    # If-Match: * => update an existing row only; never create.
    resp = session.patch(url, json=body, headers={"If-Match": "*"})
    resp.raise_for_status()
    return resp


# ── data fetching (reads) ─────────────────────────────────────────────────────────
def fetch_mice(session: requests.Session, *, only_missing: bool = True) -> List[Dict]:
    """Return [{mouse_id, guid, current_protocol_value}] from aibs_dim_mices."""
    rows = query_dataverse(
        session,
        MICE_ENTITY_SET,
        select=f"{MICE_ID_FIELD},{MICE_GUID_FIELD},{IACUC_PROTOCOL_VALUE_FIELD}",
    )
    mice = []
    for r in rows:
        mid, guid = r.get(MICE_ID_FIELD), r.get(MICE_GUID_FIELD)
        if not (mid and guid):
            continue
        current = r.get(IACUC_PROTOCOL_VALUE_FIELD)
        if only_missing and current:  # already has a protocol -> skip (client-side; ne-null filter 404s)
            continue
        mice.append({"mouse_id": str(mid), "guid": str(guid), "current_protocol_value": current})
    return mice


def _numeric_key(value) -> Optional[str]:
    """Leading digits of a protocol id ('2414-Westlake' -> '2414', '2414' -> '2414')."""
    m = re.match(r"\s*(\d+)", str(value))
    return m.group(1) if m else None


def fetch_protocol_guid_map(session: requests.Session) -> Dict[str, str]:
    """Build {numeric protocol key -> aibs_dim_iacuc_protocolsid GUID}."""
    rows = query_dataverse(
        session, IACUC_ENTITY_SET, select=f"{IACUC_ID_FIELD},{IACUC_GUID_FIELD}"
    )
    mapping: Dict[str, str] = {}
    for r in rows:
        pid, guid = r.get(IACUC_ID_FIELD), r.get(IACUC_GUID_FIELD)
        if not (pid and guid):
            continue
        key = _numeric_key(pid)
        if not key:  # e.g. "TEST_IACUC_Protocol" — no numeric form, skip
            continue
        if key in mapping and mapping[key] != str(guid):
            logger.warning("protocol number %s maps to >1 Dataverse row; keeping first", key)
            continue
        mapping[key] = str(guid)
    return mapping


# ── planning (pure; unit-testable, no network) ───────────────────────────────────
PlanItem = Dict[str, str]  # {mouse_id, mouse_guid, protocol, protocol_guid}


def build_plan(
    mice: List[Dict],
    protocol_guid_map: Dict[str, str],
    lookup_fn: Callable[[str], Optional[str]],
    *,
    overwrite: bool = False,
) -> Tuple[List[PlanItem], int, List[str], List[Tuple[str, str]]]:
    """Decide what to PATCH.

    Returns (plan, skipped_existing, no_protocol_found, unmatched_protocol) where
    unmatched_protocol is [(mouse_id, looked_up_protocol)] not present in Dataverse.
    """
    plan: List[PlanItem] = []
    skipped_existing = 0
    no_protocol: List[str] = []
    unmatched: List[Tuple[str, str]] = []

    for m in mice:
        if m.get("current_protocol_value") and not overwrite:
            skipped_existing += 1
            continue
        protocol = lookup_fn(m["mouse_id"])
        if not protocol:
            no_protocol.append(m["mouse_id"])
            continue
        guid = protocol_guid_map.get(_numeric_key(protocol) or "")
        if not guid:
            unmatched.append((m["mouse_id"], protocol))
            continue
        plan.append(
            {
                "mouse_id": m["mouse_id"],
                "mouse_guid": m["guid"],
                "protocol": protocol,
                "protocol_guid": guid,
            }
        )
    return plan, skipped_existing, no_protocol, unmatched


# ── orchestration ─────────────────────────────────────────────────────────────────
def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    fileh = logging.FileHandler(log_dir / f"iacuc_backfill_{ts}.log", encoding="utf-8")
    fileh.setFormatter(fmt)
    root.addHandler(fileh)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--apply", action="store_true",
                   help=f"Perform writes. Requires {WRITE_CONFIRM_ENV}=1 too. Omit for a dry run.")
    p.add_argument("--overwrite", action="store_true",
                   help="Also update mice that already have a protocol set.")
    p.add_argument("--top", type=int, default=None,
                   help="Process only the first N mice (handy for test dry runs).")
    p.add_argument("--subject-ids", type=Path, default=None,
                   help="JSON array of subject IDs to restrict to (default: all mice).")
    p.add_argument("--no-fallback", action="store_true",
                   help="DocDB only for the lookup; skip the slow metadata-service fallback.")
    p.add_argument("--env-file", type=Path, default=None, help="Path to a .env to load.")
    p.add_argument("--log-dir", type=Path, default=Path(__file__).parent)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_dir)

    if args.apply and os.getenv(WRITE_CONFIRM_ENV) != "1":
        logger.error(
            "--apply given but %s != 1. Refusing to run a write that can't write. "
            "Set the env var to confirm, or drop --apply for a dry run.", WRITE_CONFIRM_ENV,
        )
        return 2
    mode = "APPLY (writes enabled)" if args.apply else "DRY RUN (no writes)"
    logger.info("=== IACUC protocol backfill (lookup-sourced) — %s ===", mode)

    # env + auth (reads)
    if load_dotenv is not None:
        load_dotenv(args.env_file) if args.env_file else load_dotenv()
    missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        return 2
    session = make_session(get_access_token())
    logger.info("Dataverse: %s", _api_base())

    # fetch target mice
    mice = fetch_mice(session, only_missing=not args.overwrite)
    logger.info(
        "mice in %s %s: %d",
        MICE_ENTITY_SET,
        "with empty protocol" if not args.overwrite else "(all)",
        len(mice),
    )
    if args.subject_ids:
        wanted = {str(x) for x in json.loads(Path(args.subject_ids).read_text())}
        before = len(mice)
        mice = [m for m in mice if m["mouse_id"] in wanted]
        logger.info("restricted to --subject-ids: %d of %d", len(mice), before)
    if args.top is not None:
        mice = mice[: max(0, args.top)]
        logger.info("limited to --top %d", len(mice))

    # protocol number -> GUID map
    protocol_map = fetch_protocol_guid_map(session)
    logger.info("Dataverse protocols mapped by number: %d", len(protocol_map))

    # build the plan (this performs the per-mouse lookups)
    def lookup_fn(sid: str) -> Optional[str]:
        return get_iacuc_id_for_mouse(sid, allow_fallback=not args.no_fallback)

    plan, skipped_existing, no_protocol, unmatched = build_plan(
        mice, protocol_map, lookup_fn, overwrite=args.overwrite
    )
    logger.info(
        "plan: %d update(s) | %d already-set skipped | %d no-protocol-found | %d unmatched-protocol",
        len(plan), skipped_existing, len(no_protocol), len(unmatched),
    )
    if no_protocol:
        logger.info("  no protocol found (first 10): %s", no_protocol[:10])
    if unmatched:
        logger.info("  protocol not in Dataverse (first 10): %s", unmatched[:10])

    # dry run vs apply
    if not args.apply:
        for item in plan[:25]:
            logger.info(
                "DRY RUN would PATCH %s(%s): %s -> %s (%s)",
                MICE_ENTITY_SET, item["mouse_guid"], item["mouse_id"],
                item["protocol"], item["protocol_guid"],
            )
        if len(plan) > 25:
            logger.info("  … and %d more", len(plan) - 25)
        logger.info("DRY RUN complete — %d update(s) NOT sent.", len(plan))
        return 0

    updated = failed = 0
    for item in plan:
        try:
            patch_mouse_protocol(session, item["mouse_guid"], item["protocol_guid"])
            logger.info("Updated %s -> %s", item["mouse_id"], item["protocol"])
            updated += 1
        except requests.RequestException as exc:
            failed += 1
            logger.error("FAILED %s -> %s: %s", item["mouse_id"], item["protocol"], exc)
            if getattr(exc, "response", None) is not None:
                logger.error("Response body: %s", exc.response.text)
    logger.info("=" * 60)
    logger.info("Backfill complete — updated=%d failed=%d", updated, failed)
    logger.info("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
