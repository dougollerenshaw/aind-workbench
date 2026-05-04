"""
Read assets.json produced by lcne-paper-asset-dashboard's poll_assets.py
and write a deduped lc_paper_assets.csv with one row per unique asset.

Run lcne-paper-asset-dashboard/code/poll_assets.py first to refresh the
underlying assets.json.
"""

import json
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
LCNE_ASSETS_JSON = Path.home() / "code" / "lcne-paper-asset-dashboard" / "code" / "assets.json"
OUTPUT_FILE = SCRIPT_DIR / "lc_paper_assets.csv"


def main():
    with open(LCNE_ASSETS_JSON) as f:
        records = json.load(f)
    print(f"Read {len(records):,} records from {LCNE_ASSETS_JSON}")

    df = pd.DataFrame(records)
    df = df[df["asset_name"].notna()]

    # One row per unique asset_name; aggregate capsule_names + co_asset_ids
    grouped = (
        df.groupby("asset_name")
        .agg(
            capsule_names=("capsule_name", lambda s: ", ".join(sorted(set(s)))),
            co_asset_ids=("co_asset_id", lambda s: ", ".join(sorted(set(s)))),
            bucket=("bucket", "first"),
            bucket_status=("bucket_status", "first"),
        )
        .reset_index()
    )

    grouped.sort_values("asset_name", inplace=True)
    grouped.to_csv(OUTPUT_FILE, index=False)
    print(f"Wrote {len(grouped):,} unique assets to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
