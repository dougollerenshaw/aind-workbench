"""
Run the metadata upgrader (latest version) over the 24 assets in issue #12 and
enumerate *every* blocker that stops each asset from upgrading v1 -> v2.

Method (the "skip over single issues" approach): run the full-asset upgrade; if
it raises, record the error, neutralize the offending core field, and re-run to
surface the next blocker. Repeat until the asset upgrades cleanly or we can no
longer attribute the error to a field. This enumerates independent defects an
asset has, in the order the upgrader hits them.

If the very first upgrade succeeds, the asset "upgrades fine" with the current
upgrader and just needs to be re-run through the production pipeline.

Results are cached to out/upgrade_results.json. Run:
  uv run python run_issue12.py
"""

import copy
import json
import logging
import sys
import warnings
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "upgrader-tool"))

from upgrade import fetch_asset  # noqa: E402
from aind_metadata_upgrader.upgrade import Upgrade  # noqa: E402

# The upgrader is very chatty (recoverable validation warnings); silence it so
# the real raised errors are easy to see.
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")

CACHE = SCRIPT_DIR / "out" / "upgrade_results.json"
MAX_ITERS = 10

ASSETS = [
    "behavior_714116_2024-08-28_12-11-55",
    "behavior_714116_2024-08-29_11-46-43",
    "behavior_716325_2024-05-29_10-33-32",
    "behavior_716325_2024-05-29_10-33-32_sorted-opto_2024-09-11_22-32-12",
    "behavior_716325_2024-05-30_11-33-46",
    "behavior_716325_2024-05-30_11-33-46_sorted-opto_2024-06-04_17-00-28",
    "behavior_716325_2024-05-31_10-31-14",
    "behavior_716325_2024-05-31_10-31-14_sorted_curated_2024-07-16_06-10-19",
    "behavior_716325_2024-05-31_10-31-14_sorted-opto-ZS_2024-06-05_03-54-32",
    "behavior_716325_2024-06-01_09-25-37",
    "behavior_716325_2024-06-01_09-25-37_sorted-opto-bandpass_2024-09-10_13-10-02",
    "behavior_717121_2024-06-11_10-23-31",
    "behavior_717121_2024-06-15_10-00-58",
    "behavior_717259_2024-06-28_11-17-19",
    "behavior_717263_2024-07-24_10-40-05",
    "behavior_722832_2024-09-13_11-55-58",
    "behavior_724172_2024-10-01_11-20-11",
    "behavior_724172_2024-10-03_11-02-53",
    "behavior_739970_2024-10-15_10-04-12",
    "behavior_739970_2024-10-16_12-15-24",
    "behavior_739977_2024-10-24_12-58-26",
    "behavior_751766_2025-02-13_11-31-21",
    "behavior_751766_2025-02-14_11-37-11",
    "behavior_751766_2025-02-15_12-08-11",
]

# v1 core field -> which error texts implicate it
FIELD_FROM_ERROR = [
    ("processing", ("DataProcess", "processing_pipeline", "Processing")),
    ("data_description", ("Unsupported funder", "Funding", "DataDescription")),
    ("procedures", ("Procedures", "Surgery")),
    ("subject", ("for Subject",)),
    ("session", ("Acquisition", "for Session", "Stream")),
    ("rig", ("Instrument", "for Rig")),
]


def field_from_error(msg):
    for field, needles in FIELD_FROM_ERROR:
        if any(n in msg for n in needles):
            return field
    return None


def enumerate_blockers(asset_data):
    """Return (upgrades_fine, blockers, stuck_error)."""
    remaining = copy.deepcopy(asset_data)
    blockers = []
    for _ in range(MAX_ITERS):
        try:
            Upgrade(remaining).metadata.model_dump()
            return (len(blockers) == 0), blockers, None
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            field = field_from_error(msg)
            blockers.append({
                "field": field or "(unknown)",
                "error_first_line": next((l.strip() for l in msg.splitlines() if l.strip()), msg)[:200],
                "error_full": msg,
            })
            if not field or remaining.get(field) is None:
                return False, blockers, msg.splitlines()[0][:200]
            remaining[field] = None  # neutralize and look for the next blocker
    return False, blockers, "exceeded MAX_ITERS"


def main():
    results = {}
    for i, name in enumerate(ASSETS, 1):
        print(f"[{i}/{len(ASSETS)}] {name}", flush=True)
        asset = fetch_asset(name, "name")
        if not asset:
            results[name] = {"found": False}
            print("    NOT FOUND in v1 docdb", flush=True)
            continue
        upgrades_fine, blockers, stuck = enumerate_blockers(asset)
        results[name] = {
            "found": True,
            "upgrades_fine": upgrades_fine,
            "blockers": blockers,
            "stuck": stuck,
        }
        if upgrades_fine:
            print("    UPGRADES FINE", flush=True)
        else:
            print(f"    blockers: {[b['field'] for b in blockers]}"
                  + (f"  STUCK: {stuck}" if stuck else ""), flush=True)

    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {CACHE}")


if __name__ == "__main__":
    main()
