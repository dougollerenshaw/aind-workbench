"""
Query DocDB for dynamic foraging behavior assets and attach them to a capsule.

Run with:
    uv run attach_assets.py
"""
from collections import defaultdict
from pathlib import Path
import os

import requests
from dotenv import load_dotenv
from tqdm import tqdm
from codeocean import CodeOcean
from codeocean.data_asset import DataAsset, DataAssetSearchParams
from codeocean.capsule import DataAssetAttachParams

load_dotenv(Path(__file__).parent.parent.parent / ".env")

CO_DOMAIN = "https://codeocean.allenneuraldynamics.org"
CAPSULE_ID = "099d1d69-c586-4a99-ac85-fb12963a25cd"
MAX_PER_SUBJECT = 25
SUBJECT_IDS = ["775741", "756403", "751181", "770772", "751765"]

DOCDB_PIPELINE = [
    {"$match": {
        "data_description.data_level": "derived",
        "data_description.modality.abbreviation": "behavior",
        "data_description.project_name": "Behavior Platform",
        "subject.subject_id": {"$in": SUBJECT_IDS},
    }},
    {"$project": {
        "_id": 0, "name": 1, "created": 1,
        "subject.subject_id": 1,
        "data_description.input_data_name": 1,
    }},
]


def query_docdb(pipeline: list[dict]) -> list[dict]:
    """Run a MongoDB aggregation pipeline against the DocDB metadata index.

    Returns a list of raw record dicts matching the pipeline criteria.
    """
    resp = requests.post(
        "https://api.allenneuraldynamics.org/v1/metadata_index/data_assets/aggregate",
        json=pipeline,
    )
    resp.raise_for_status()
    return resp.json()


def dedup_records(
    records: list[dict], subject_ids: list[str], max_per_subject: int
) -> list[dict]:
    """Deduplicate and cap records per subject.

    For each subject, groups records by their source session (input_data_name).
    Within each group, keeps only the most recently created processing run.
    Returns up to max_per_subject records per subject, sorted by session date.
    """
    per_subject = defaultdict(list)
    for r in records:
        sid = r.get("subject", {}).get("subject_id", "unknown")
        per_subject[sid].append(r)

    selected = []
    for sid in subject_ids:
        by_source = defaultdict(list)
        for r in per_subject[sid]:
            source = r.get("data_description", {}).get("input_data_name", r["name"])
            by_source[source].append(r)

        deduped = sorted(
            [max(v, key=lambda r: r.get("created", "")) for v in by_source.values()],
            key=lambda r: r.get("data_description", {}).get("input_data_name", r["name"]),
        )[:max_per_subject]

        print(f"  Subject {sid}: {len(per_subject[sid])} raw → {len(deduped)} selected")
        selected.extend(deduped)

    return selected


def resolve_co_assets(names: list[str], client: CodeOcean) -> list[DataAsset]:
    """Look up asset names in Code Ocean and return the matching DataAsset objects.

    Prints a warning for any names not found. Resolved assets are returned in the
    same order as the input names.
    """
    assets = []
    for name in tqdm(names, desc="Resolving assets", unit="asset"):
        results = client.data_assets.search_data_assets(DataAssetSearchParams(query=name))
        match = next((a for a in results.results if a.name == name), None)
        if match:
            assets.append(match)
        else:
            tqdm.write(f"Not found in Code Ocean: {name}")
    return assets


def attach_assets(assets: list[DataAsset], capsule_id: str, client: CodeOcean) -> None:
    """Attach a list of Code Ocean DataAssets to a capsule in a single API call."""
    client.capsules.attach_data_assets(
        capsule_id,
        [DataAssetAttachParams(id=a.id, mount=a.name) for a in assets],
    )
    print(f"Attached {len(assets)} assets to capsule {capsule_id}")


if __name__ == "__main__":
    client = CodeOcean(domain=CO_DOMAIN, token=os.environ["code_ocean_api_key"])

    records = query_docdb(DOCDB_PIPELINE)
    print(f"DocDB records: {len(records)}")

    selected = dedup_records(records, SUBJECT_IDS, MAX_PER_SUBJECT)
    print(f"Selected {len(selected)} sessions total\n")

    assets = resolve_co_assets([r["name"] for r in selected], client)
    attach_assets(assets, CAPSULE_ID, client)
