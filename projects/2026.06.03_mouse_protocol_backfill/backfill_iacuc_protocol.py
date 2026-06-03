# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests>=2.31",
#   "msal>=1.28",
#   "python-dotenv>=1.0",
# ]
# ///
"""
Backfill the ``aibs_iacuc_protocol`` lookup on the Dataverse ``aibs_dim_mice`` table.

Given a CSV of ``subject_id, iacuc_protocol_id`` rows, this script:

  1. Reads + validates the CSV (one protocol per mouse).
  2. Resolves each protocol id (e.g. ``2301-Westlake``) to its row GUID in
     ``aibs_dim_iacuc_protocolses``.
  3. Resolves each subject/mouse id to its row GUID in ``aibs_dim_mices`` (and reads
     the current protocol value so already-populated mice can be skipped).
  4. PATCHes each mouse record, binding the protocol lookup via ``@odata.bind``.

It is **dry-run by default** — it resolves everything and logs exactly what *would*
be written, but sends nothing. Pass ``--apply`` to perform the writes.

The auth / query / lookup-binding conventions here mirror
``AllenNeuralDynamics/aind-dataverse-migration-scripts`` (the same MSAL flow, the same
``/api/data/v9.2`` Web API, the same ``"<nav>@odata.bind": "/entityset(guid)"`` idiom).
The one piece that repo lacks is an *update* path — its loaders only POST/create and
skip existing rows — so the PATCH-by-GUID helper below is the new bit. The ~1156 mice
already exist with a null protocol, so they must be updated, not created.

Usage (uv resolves the inline deps automatically):

    # Offline CSV check — no network, no auth required:
    uv run backfill_iacuc_protocol.py --validate-only

    # Dry run against Dataverse (needs read auth) — review the plan:
    uv run backfill_iacuc_protocol.py

    # Apply the writes (needs write auth):
    uv run backfill_iacuc_protocol.py --apply

Required environment variables (a .env file in this dir is auto-loaded):
    DATAVERSE_CLIENT_ID, DATAVERSE_TENANT_ID, DATAVERSE_HOST,
    DATAVERSE_USERNAME, DATAVERSE_PASSWORD
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

try:  # optional; only needed to auto-load a .env file
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


# ── Dataverse schema constants ────────────────────────────────────────────────
API_VERSION = "v9.2"

MICE_ENTITY_SET = "aibs_dim_mices"
MICE_ID_FIELD = "aibs_mouse_id"
MICE_GUID_FIELD = "aibs_dim_miceid"

IACUC_ENTITY_SET = "aibs_dim_iacuc_protocolses"
IACUC_ID_FIELD = "aibs_protocol_id"
IACUC_GUID_FIELD = "aibs_dim_iacuc_protocolsid"

# Single-valued navigation property used in the @odata.bind payload. It corresponds
# to the lookup column whose stored value field is ``_aibs_iacuc_protocol_value``.
# This is almost certainly correct, but the navigation-property name can differ from
# the attribute logical name in Dataverse — VERIFY once against
#   {DATAVERSE_HOST}/api/data/v9.2/$metadata
# (search for the EntityType "aibs_dim_mice" -> NavigationProperty) before the first
# real --apply run. A wrong name yields a 400 on PATCH, which the dry run cannot catch.
IACUC_PROTOCOL_NAV = "aibs_iacuc_protocol"
IACUC_PROTOCOL_VALUE_FIELD = "_aibs_iacuc_protocol_value"
_FORMATTED = "@OData.Community.Display.V1.FormattedValue"

REQUIRED_ENV = [
    "DATAVERSE_CLIENT_ID",
    "DATAVERSE_TENANT_ID",
    "DATAVERSE_HOST",
    "DATAVERSE_USERNAME",
    "DATAVERSE_PASSWORD",
]

ODATA_FILTER_CHUNK = 20  # ids per $filter expression, to keep request URLs short

logger = logging.getLogger("iacuc_backfill")


# ── auth + http ───────────────────────────────────────────────────────────────
def get_access_token() -> str:
    """Acquire a Dataverse access token via the MSAL username/password flow."""
    import msal  # imported lazily so --validate-only needs no auth deps

    missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    host = os.getenv("DATAVERSE_HOST", "").rstrip("/")
    authority = f"https://login.microsoftonline.com/{os.getenv('DATAVERSE_TENANT_ID')}"
    scopes = [f"{host}/user_impersonation"]

    app = msal.PublicClientApplication(
        client_id=os.getenv("DATAVERSE_CLIENT_ID"), authority=authority
    )
    logger.info("Acquiring Dataverse access token ...")
    result = app.acquire_token_by_username_password(
        username=os.getenv("DATAVERSE_USERNAME"),
        password=os.getenv("DATAVERSE_PASSWORD"),
        scopes=scopes,
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
            # Return human-readable values for lookups/choices in GET responses.
            "Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"',
        }
    )
    return session


def api_base() -> str:
    return f"{os.getenv('DATAVERSE_HOST', '').rstrip('/')}/api/data/{API_VERSION}"


def query_dataverse(
    session: requests.Session,
    entity_set: str,
    *,
    select: str,
    filter_str: Optional[str] = None,
) -> List[Dict]:
    """GET rows from an entity set, following ``@odata.nextLink`` paging."""
    params: Dict[str, str] = {"$select": select}
    if filter_str:
        params["$filter"] = filter_str
    url: Optional[str] = f"{api_base()}/{entity_set}"
    out: List[Dict] = []
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        out.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
        params = {}  # nextLink already carries the query
    return out


def patch_mouse_protocol(
    session: requests.Session, mouse_guid: str, protocol_guid: str
) -> requests.Response:
    """Bind the IACUC protocol lookup on a single mouse record (update-only)."""
    url = f"{api_base()}/{MICE_ENTITY_SET}({mouse_guid})"
    body = {f"{IACUC_PROTOCOL_NAV}@odata.bind": f"/{IACUC_ENTITY_SET}({protocol_guid})"}
    # If-Match: * => update an existing row only; never create. Guards against a
    # mistyped GUID silently upserting a brand-new (orphan) record.
    resp = session.patch(url, json=body, headers={"If-Match": "*"})
    resp.raise_for_status()
    return resp


# ── helpers ─────────────────────────────────────────────────────────────────
def _chunks(items: List[str], n: int) -> Iterable[List[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _odata_str(value: str) -> str:
    """Escape single quotes for use inside an OData string literal."""
    return value.replace("'", "''")


# ── CSV ───────────────────────────────────────────────────────────────────────
def read_csv(path: Path, subject_col: str, protocol_col: str) -> List[Tuple[str, str]]:
    """Parse the input CSV into a list of (subject_id, protocol_id) pairs."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = [h.strip() for h in (reader.fieldnames or [])]
        if subject_col not in fields or protocol_col not in fields:
            raise ValueError(
                f"CSV must contain columns '{subject_col}' and '{protocol_col}'. "
                f"Found: {reader.fieldnames}"
            )
        pairs: List[Tuple[str, str]] = []
        for lineno, raw in enumerate(reader, start=2):  # line 1 is the header
            # tolerate stray whitespace in header names
            row = {(k or "").strip(): v for k, v in raw.items()}
            subject = (row.get(subject_col) or "").strip()
            protocol = (row.get(protocol_col) or "").strip()
            if not subject and not protocol:
                continue  # blank line
            if not subject or not protocol:
                logger.warning(
                    "Line %d: missing subject or protocol (%r, %r) — skipping",
                    lineno, subject, protocol,
                )
                continue
            pairs.append((subject, protocol))
    return pairs


def dedupe(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """Collapse to one protocol per mouse (last wins), warning on conflicts."""
    mapping: Dict[str, str] = {}
    for subject, protocol in pairs:
        if subject in mapping and mapping[subject] != protocol:
            logger.warning(
                "Subject %s appears with conflicting protocols (%s, %s); using %s",
                subject, mapping[subject], protocol, protocol,
            )
        mapping[subject] = protocol
    return mapping


# ── resolution ──────────────────────────────────────────────────────────────
def resolve_protocol_guids(
    session: requests.Session, protocol_ids: Iterable[str]
) -> Dict[str, str]:
    """Map protocol id (e.g. '2301-Westlake') -> aibs_dim_iacuc_protocolsid GUID."""
    wanted = sorted(set(protocol_ids))
    out: Dict[str, str] = {}
    for chunk in _chunks(wanted, ODATA_FILTER_CHUNK):
        filt = " or ".join(f"{IACUC_ID_FIELD} eq '{_odata_str(p)}'" for p in chunk)
        for rec in query_dataverse(
            session, IACUC_ENTITY_SET,
            select=f"{IACUC_ID_FIELD},{IACUC_GUID_FIELD}", filter_str=filt,
        ):
            pid, guid = rec.get(IACUC_ID_FIELD), rec.get(IACUC_GUID_FIELD)
            if pid and guid:
                out[str(pid)] = str(guid)
    return out


def resolve_mouse_records(
    session: requests.Session, subject_ids: Iterable[str]
) -> Dict[str, Dict]:
    """Map subject id -> {guid, current_protocol_value, current_protocol_name}."""
    wanted = sorted(set(subject_ids))
    out: Dict[str, Dict] = {}
    select = f"{MICE_ID_FIELD},{MICE_GUID_FIELD},{IACUC_PROTOCOL_VALUE_FIELD}"
    for chunk in _chunks(wanted, ODATA_FILTER_CHUNK):
        filt = " or ".join(f"{MICE_ID_FIELD} eq '{_odata_str(s)}'" for s in chunk)
        for rec in query_dataverse(session, MICE_ENTITY_SET, select=select, filter_str=filt):
            sid, guid = rec.get(MICE_ID_FIELD), rec.get(MICE_GUID_FIELD)
            if sid and guid:
                out[str(sid)] = {
                    "guid": str(guid),
                    "current_protocol_value": rec.get(IACUC_PROTOCOL_VALUE_FIELD),
                    "current_protocol_name": rec.get(
                        IACUC_PROTOCOL_VALUE_FIELD + _FORMATTED
                    ),
                }
    return out


# ── orchestration ─────────────────────────────────────────────────────────────
def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"iacuc_backfill_{ts}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    fileh = logging.FileHandler(log_file, encoding="utf-8")
    fileh.setFormatter(fmt)
    logger.addHandler(fileh)
    logger.info("Logging to %s", log_file)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    default_csv = Path(__file__).with_name("sample_mouse_protocol.csv")
    p.add_argument("--csv", type=Path, default=default_csv,
                   help="Input CSV (default: bundled sample_mouse_protocol.csv).")
    p.add_argument("--subject-col", default="subject_id", help="CSV subject-id column name.")
    p.add_argument("--protocol-col", default="iacuc_protocol_id",
                   help="CSV protocol-id column name.")
    p.add_argument("--apply", action="store_true",
                   help="Perform the writes. Omit for a dry run (the default).")
    p.add_argument("--overwrite", action="store_true",
                   help="Also update mice that already have a protocol set.")
    p.add_argument("--top", type=int, default=None,
                   help="Process only the first N (deduped) subjects.")
    p.add_argument("--validate-only", action="store_true",
                   help="Parse/validate the CSV and exit. No network, no auth.")
    p.add_argument("--env-file", type=Path, default=None,
                   help="Path to a .env file to load (default: ./.env if present).")
    p.add_argument("--log-dir", type=Path, default=Path(__file__).parent,
                   help="Directory for the timestamped run log.")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_dir)

    mode = "APPLY (writes enabled)" if args.apply else "DRY RUN (no writes)"
    logger.info("=== IACUC protocol backfill — %s ===", mode)

    # 1) CSV ------------------------------------------------------------------
    pairs = read_csv(args.csv, args.subject_col, args.protocol_col)
    mapping = dedupe(pairs)
    if args.top is not None:
        mapping = dict(list(mapping.items())[: max(0, args.top)])
    logger.info("CSV %s -> %d unique subject(s)", args.csv, len(mapping))
    if not mapping:
        logger.warning("Nothing to do.")
        return 0

    if args.validate_only:
        for sid, pid in mapping.items():
            logger.info("  %s -> %s", sid, pid)
        logger.info("validate-only: parsed %d row(s); no network calls made.", len(mapping))
        return 0

    # 2) env + auth -----------------------------------------------------------
    if load_dotenv is not None:
        load_dotenv(args.env_file) if args.env_file else load_dotenv()
    elif args.env_file:
        logger.warning("python-dotenv not installed; --env-file ignored.")
    missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        return 2

    session = make_session(get_access_token())
    logger.info("Authenticated to %s", api_base())

    # 3) resolve ids to GUIDs -------------------------------------------------
    protocol_guids = resolve_protocol_guids(session, mapping.values())
    mouse_records = resolve_mouse_records(session, mapping.keys())

    unknown_protocols = sorted({p for p in mapping.values() if p not in protocol_guids})
    unknown_mice = sorted({s for s in mapping if s not in mouse_records})
    if unknown_protocols:
        logger.warning("%d protocol id(s) not found in %s: %s",
                       len(unknown_protocols), IACUC_ENTITY_SET, unknown_protocols)
    if unknown_mice:
        logger.warning("%d subject id(s) not found in %s: %s",
                       len(unknown_mice), MICE_ENTITY_SET, unknown_mice)

    # 4) build the plan -------------------------------------------------------
    plan: List[Tuple[str, str, str, str]] = []  # (subject, protocol, mouse_guid, proto_guid)
    skipped_existing = skipped_unresolved = 0
    for sid, pid in mapping.items():
        rec = mouse_records.get(sid)
        pguid = protocol_guids.get(pid)
        if rec is None or pguid is None:
            skipped_unresolved += 1
            continue
        current = rec.get("current_protocol_value")
        if current and not args.overwrite:
            if str(current) == str(pguid):
                logger.info("Skip %s: protocol already set to %s", sid, pid)
            else:
                logger.warning(
                    "Skip %s: already has a different protocol (%s) — use --overwrite to replace.",
                    sid, rec.get("current_protocol_name") or current,
                )
            skipped_existing += 1
            continue
        plan.append((sid, pid, rec["guid"], pguid))

    logger.info(
        "Plan: %d update(s); skipped %d already-set, %d unresolved.",
        len(plan), skipped_existing, skipped_unresolved,
    )

    # 5) execute (or dry run) -------------------------------------------------
    if not args.apply:
        for sid, pid, mguid, pguid in plan:
            logger.info(
                "DRY RUN would PATCH %s(%s): bind %s -> %s (%s)",
                MICE_ENTITY_SET, mguid, IACUC_PROTOCOL_NAV, pid, pguid,
            )
        logger.info(
            "DRY RUN complete — %d update(s) NOT sent. Re-run with --apply to write.",
            len(plan),
        )
        return 0

    updated = failed = 0
    for sid, pid, mguid, pguid in plan:
        try:
            patch_mouse_protocol(session, mguid, pguid)
            logger.info("Updated %s -> %s", sid, pid)
            updated += 1
        except requests.RequestException as exc:
            failed += 1
            logger.error("FAILED %s -> %s: %s", sid, pid, exc)
            if getattr(exc, "response", None) is not None:
                logger.error("Response body: %s", exc.response.text)

    logger.info("=" * 60)
    logger.info(
        "Backfill complete — updated=%d failed=%d skipped=%d",
        updated, failed, skipped_existing + skipped_unresolved,
    )
    logger.info("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
