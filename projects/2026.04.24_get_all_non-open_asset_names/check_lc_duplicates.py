"""
For each duplicate-name asset listed in
https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/721,
check which of the duplicates is actually attached to an LC paper capsule
(matching on code_ocean_external_link / co_asset_id, not name).

Reads assets.json from the lcne-paper-asset-dashboard clone.
"""

import json
from collections import defaultdict
from pathlib import Path

LCNE_ASSETS_JSON = Path.home() / "code" / "lcne-paper-asset-dashboard" / "code" / "assets.json"

# Pasted from issue #721 comment
DUPLICATES = {
    "behavior_751004_2024-12-23_14-19-57_videoprocessed_2025-10-24_21-43-19": [
        "f815fc68-6f70-4333-9cb4-cef60a922542",
        "41235f40-e714-48f1-8bb9-dd4298d68271",
        "cf0243b5-8da2-4390-be66-c861bc65d6a6",
    ],
    "behavior_751181_2025-02-27_11-24-44_videoprocessed_2025-10-24_21-43-19": [
        "2e3d9361-3347-48a4-9fac-e0180450db4b",
        "4f5c31bc-25fa-43ea-97d2-7ed63dad3b00",
        "ae5f98b1-f883-4615-825b-cfeb6a2ed43b",
    ],
    "behavior_754897_2025-03-13_11-20-39_videoprocessed_2025-10-24_21-43-19": [
        "a93392f6-734c-4541-8a17-3bf9db5c3eb0",
        "e8d10833-721e-49e5-838a-0a59aecf0784",
    ],
    "behavior_758017_2025-02-04_11-57-33_videoprocessed_2025-10-24_21-43-19": [
        "81b5ec4d-4772-4d6b-8a70-f13651d1c4d2",
        "5675b15a-66d6-4434-a67a-7cdb909e8489",
        "ee715277-4a5c-4163-94ef-88783b1eebe0",
    ],
    "behavior_761038_2025-04-15_10-24-57_videoprocessed_2025-10-24_21-43-19": [
        "7d7f1202-c493-487d-b10a-a7db0d857e58",
        "0ef342f6-d5cf-438d-8f7b-cb2d0f7f3e77",
    ],
    "behavior_782394_2025-04-23_10-51-14_videoprocessed_2025-10-24_21-43-19": [
        "2f85bc06-1538-443f-9462-1a6ca60a76af",
        "92bad8b7-32c5-4ff4-8c0d-72c9c3555ec0",
    ],
}


def main():
    with open(LCNE_ASSETS_JSON) as f:
        records = json.load(f)

    # Build map: co_asset_id -> set of capsule names
    id_to_capsules = defaultdict(set)
    for r in records:
        cid = r.get("co_asset_id")
        cap = r.get("capsule_name")
        if cid and cap:
            id_to_capsules[cid].add(cap)

    print(f"LC paper dashboard tracks {len(id_to_capsules):,} unique co_asset_ids\n")
    print("=" * 80)

    for name, asset_ids in DUPLICATES.items():
        print(f"\n{name}")
        print(f"  ({len(asset_ids)} duplicates)")
        for aid in asset_ids:
            capsules = id_to_capsules.get(aid)
            if capsules:
                print(f"    [LC PAPER]   {aid}")
                for cap in sorted(capsules):
                    print(f"                   used by: {cap}")
            else:
                print(f"    [not in LC]  {aid}")


if __name__ == "__main__":
    main()
