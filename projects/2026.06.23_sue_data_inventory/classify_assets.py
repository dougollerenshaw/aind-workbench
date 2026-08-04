"""
Classify Sue's session assets for open-data migration.

Reads the session-assets spreadsheet, looks each asset up in the AIND metadata
DocDB by EXACT NAME (v2 first, then v1), and writes a `status` column plus
diagnostics that sort every asset into a finite set of action buckets.

Matching is exact-name-only. A name that isn't present in DocDB is NOT_FOUND
(that's a problem to surface, not something to fuzzy-match around). Read-only.

Usage:
  uv run python classify_assets.py            # full run (uses cache if present)
  uv run python classify_assets.py --no-cache # ignore cache, re-query everything
  uv run python classify_assets.py --selftest # only run the §8 self-test assets
  uv run python classify_assets.py --limit N  # first N rows + self-test assets
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient

SCRIPT_DIR = Path(__file__).parent
INPUT_FILE = SCRIPT_DIR / "session_assets_sources_with_FP.csv"
OUTPUT_CSV = SCRIPT_DIR / "session_assets_status.csv"
OUT_DIR = SCRIPT_DIR / "out"
CACHE_FILE = OUT_DIR / "docdb_cache.json"

HOST = "api.allenneuraldynamics.org"
PROJECTION = {"_id": 1, "name": 1, "location": 1, "data_description": 1, "processing": 1}
NAME_CHUNK = 100
OPEN_DATA_PREFIX = "s3://aind-open-data/"

CLIENT_V2 = MetadataDbClient(host=HOST, version="v2")
CLIENT_V1 = MetadataDbClient(host=HOST, version="v1")

# Edge case (§6): an asset in open-data but found ONLY in v1.
# True  -> classify ALREADY_OPEN_DATA, flag v1_only (recommended default).
# False -> classify V1_NOT_V2.
OPEN_DATA_V1_COUNTS_AS_DONE = True

# §8 self-test expectations (exact-name matching).
SELFTEST = {
    "f2029505-5cc9-4889-9bd6-5d80d4d6079a": "ALREADY_OPEN_DATA",
    "75f7920a-17c9-4e0c-8259-aee69e0544b2": "ALREADY_OPEN_DATA",
    "1c147ab8-4465-4684-bc58-448f9ba6a7aa": "ALREADY_OPEN_DATA",
    "17acbbc8-35e6-499d-b27f-1a21812f4070": "READY_TO_MOVE",
    "4699a15c-c8a7-47ab-b288-2a5768530d16": "V1_NOT_V2",
    "0438b3fa-3ddc-45ba-9c95-9ce2baf71b93": "NOT_FOUND",  # exact name not registered
    "c712751d-f744-4fe8-9657-93a7084eab22": "NOT_FOUND",
}


def _batch_by_name(client, names):
    """Exact-name $in lookup, chunked. Returns {name: [records]}."""
    out = {}
    for i in range(0, len(names), NAME_CHUNK):
        chunk = names[i : i + NAME_CHUNK]
        for attempt in range(4):
            try:
                recs = client.fetch_records_by_filter_list(
                    "name", chunk, projection=PROJECTION
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 3:
                    raise
                wait = 2**attempt
                print(f"    batch failed ({exc}); retry in {wait}s")
                time.sleep(wait)
        for r in recs:
            out.setdefault(r.get("name"), []).append(r)
    return out


def _slim(rec):
    """Keep only what we need from a DocDB record; coerce null->missing."""
    return {
        "_id": rec.get("_id"),
        "name": rec.get("name"),
        "location": rec.get("location"),
        "has_data_description": rec.get("data_description") is not None,
        "has_processing": rec.get("processing") is not None,
    }


def classify(found_in, records):
    """Apply the decision tree (§6) to exact-name matches for one asset."""
    in_open_data = any((r["location"] or "").startswith(OPEN_DATA_PREFIX) for r in records)
    has_dd = any(r["has_data_description"] for r in records)
    has_proc = any(r["has_processing"] for r in records)
    v1_only = found_in == "v1"

    if found_in == "v2":
        if in_open_data:
            status = "ALREADY_OPEN_DATA"
        elif has_dd and has_proc:
            status = "READY_TO_MOVE"
        else:
            status = "NEEDS_METADATA"
    elif found_in == "v1":
        if in_open_data and OPEN_DATA_V1_COUNTS_AS_DONE:
            status = "ALREADY_OPEN_DATA"
        else:
            status = "V1_NOT_V2"
    else:
        status = "NOT_FOUND"

    # representative record: prefer open-data, else most complete, else first
    rep = None
    if records:
        rep = next((r for r in records if (r["location"] or "").startswith(OPEN_DATA_PREFIX)), None)
        if rep is None:
            rep = next((r for r in records if r["has_data_description"] and r["has_processing"]), None)
        if rep is None:
            rep = records[0]

    return {
        "status": status,
        "found_in": found_in,
        "in_open_data": in_open_data,
        "has_data_description": has_dd,
        "has_processing": has_proc,
        "n_records": len(records),
        "docdb_id": rep["_id"] if rep else "",
        "docdb_name": rep["name"] if rep else "",
        "docdb_location": rep["location"] if rep else "",
        "v1_only": v1_only,
        "api_version_used": found_in,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-cache", action="store_true", help="ignore cache")
    parser.add_argument("--selftest", action="store_true", help="only §8 self-test assets")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="process only the first N rows (plus the self-test assets)")
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(INPUT_FILE)
    if args.selftest:
        df = df[df["id"].isin(SELFTEST)].reset_index(drop=True)
    elif args.limit:
        keep = df.head(args.limit)
        extra = df[df["id"].isin(SELFTEST) & ~df["id"].isin(keep["id"])]
        df = pd.concat([keep, extra]).reset_index(drop=True)
    print(f"Loaded {len(df)} assets.")

    cache = {}
    if CACHE_FILE.exists() and not args.no_cache:
        cache = json.loads(CACHE_FILE.read_text())
        print(f"Loaded cache with {len(cache)} entries.")

    need = df if args.no_cache else df[~df["id"].isin(cache)]
    print(f"{len(need)} assets need lookup.")

    if len(need):
        names = need["name"].tolist()
        print("Batch exact-name lookup against v2...")
        hits_v2 = _batch_by_name(CLIENT_V2, names)
        misses = [n for n in names if n not in hits_v2]
        print(f"  v2 matched {len(names) - len(misses)}/{len(names)} by name.")
        print(f"Batch exact-name lookup against v1 for {len(misses)} misses...")
        hits_v1 = _batch_by_name(CLIENT_V1, misses) if misses else {}
        print(f"  v1 matched {len(hits_v1)} additional names.")

        for row in need.itertuples(index=False):
            if row.name in hits_v2:
                found_in, recs = "v2", hits_v2[row.name]
            elif row.name in hits_v1:
                found_in, recs = "v1", hits_v1[row.name]
            else:
                found_in, recs = "none", []
            cache[row.id] = {"found_in": found_in, "records": [_slim(r) for r in recs]}

        CACHE_FILE.write_text(json.dumps(cache, indent=2))
        print(f"Cache written to {CACHE_FILE}")

    # classify
    checked_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in df.itertuples(index=False):
        entry = cache[row.id]
        c = classify(entry["found_in"], entry["records"])
        c["notes"] = ""
        c["checked_at"] = checked_at
        rows.append(c)
    out = pd.concat([df, pd.DataFrame(rows, index=df.index)], axis=1)

    # self-test
    if df["id"].isin(SELFTEST).any():
        print("\n=== Self-test (§8) ===")
        ok = True
        for _id, expected in SELFTEST.items():
            sub = out[out["id"] == _id]
            if sub.empty:
                continue
            got = sub.iloc[0]["status"]
            if got != expected:
                ok = False
            print(f"  [{'OK ' if got == expected else 'FAIL'}] "
                  f"{sub.iloc[0]['name'][:55]:55} expected={expected:18} got={got}")
        print("  All self-tests passed." if ok else "  *** SELF-TEST FAILURES ***")

    # summary
    print("\n=== Status counts ===")
    for status, n in out["status"].value_counts().items():
        print(f"  {status:20} {n}")

    out.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {OUTPUT_CSV}")
    write_bucket_lists(out)


def write_bucket_lists(out):
    """One markdown task-list file per actionable bucket (§2, §10)."""
    titles = {
        "READY_TO_MOVE": "Move assets with valid metadata to aind-open-data",
        "NEEDS_METADATA": "Generate/repair metadata for assets not yet in open-data",
        "V1_NOT_V2": "Investigate assets present in DocDB v1 but not v2 (upgrade failures)",
        "NOT_FOUND": "Locate / register assets whose exact name is absent from DocDB",
    }
    for status, title in titles.items():
        sub = out[out["status"] == status]
        if sub.empty:
            continue
        lines = [f"# {title}", "", f"{len(sub)} assets.", ""]
        for r in sub.itertuples(index=False):
            loc = r.docdb_location or "not found"
            lines.append(f"- [ ] {r.name} (`{r.id}`) — {loc}")
        path = OUT_DIR / f"{status}.md"
        path.write_text("\n".join(lines) + "\n")
        print(f"  wrote {path} ({len(sub)} assets)")


if __name__ == "__main__":
    main()
