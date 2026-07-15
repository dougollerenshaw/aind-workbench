"""
Find OTHER v1 records with the same upgrade-blocking defects as the 24 in
issue #12, and confirm they are absent from v2 (i.e. genuinely stuck).

Three defect signatures (see migration_fix_spec.md):
  A. video-compression DataProcess missing start_date_time
  B. (broader) any DataProcess missing start_date_time
  C. funding_source.funder stored as a bare string (e.g. "NINMH")
  D. procedures.subject_id explicitly null

  uv run python find_similar_broken.py
"""

import json
from pathlib import Path

from aind_data_access_api.document_db import MetadataDbClient

HOST = "api.allenneuraldynamics.org"
V1 = MetadataDbClient(host=HOST, version="v1")
V2 = MetadataDbClient(host=HOST, version="v2")
OUT = Path(__file__).parent / "out" / "similar_broken.json"

FILTERS = {
    "A_video_compression_no_start": {
        "processing.processing_pipeline.data_processes": {
            "$elemMatch": {
                "code_url": {"$regex": "aind-behavior-video-transformation"},
                "start_date_time": {"$exists": False},
            }
        }
    },
    "B_any_dataprocess_no_start": {
        "processing.processing_pipeline.data_processes": {
            "$elemMatch": {"start_date_time": {"$exists": False}}
        }
    },
    "C_string_funder": {"data_description.funding_source.funder": {"$type": "string"}},
    "D_procedures_subject_id_null": {"procedures.subject_id": {"$type": "null"}},
}


def count(client, filt):
    res = client.aggregate_docdb_records(pipeline=[{"$match": filt}, {"$count": "n"}])
    return res[0]["n"] if res else 0


def names_for(client, filt):
    recs = client.retrieve_docdb_records(
        filter_query=filt, projection={"name": 1, "location": 1, "_id": 0}, limit=0
    )
    return recs


def in_v2(names):
    """Return the set of names that EXIST in v2 (exact-name match, batched)."""
    found = set()
    names = list(names)
    for i in range(0, len(names), 100):
        chunk = names[i : i + 100]
        recs = V2.fetch_records_by_filter_list("name", chunk, projection={"name": 1, "_id": 0})
        found.update(r.get("name") for r in recs)
    return found


def main():
    summary = {}
    for key, filt in FILTERS.items():
        n_v1 = count(V1, filt)
        print(f"\n=== {key}: {n_v1} records in v1 ===")
        recs = names_for(V1, filt)
        names = sorted({r["name"] for r in recs if r.get("name")})
        present_v2 = in_v2(names)
        stuck = [n for n in names if n not in present_v2]
        print(f"    {len(names)} distinct names | {len(present_v2)} already in v2 | "
              f"{len(stuck)} in v1 but NOT v2 (candidates)")
        summary[key] = {
            "n_v1": n_v1,
            "n_distinct_names": len(names),
            "n_in_v2": len(present_v2),
            "n_stuck": len(stuck),
            "stuck_names": stuck,
        }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
