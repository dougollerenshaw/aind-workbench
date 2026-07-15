"""Resolve Code Ocean capsule UUIDs (from the batch and results buckets) to names/tags.

Caches the result to capsule_map.json so the notebook can build a category column
without calling the Code Ocean API. Resolves all batch-bucket capsules plus the
results-bucket capsules that cover 99% of that bucket's size (the rest is a tiny
long tail labeled "other" downstream).

Run with the Code Ocean token loaded:
    set -a && source /Users/doug.ollerenshaw/code/.env && set +a
    uv run --with 'awswrangler[postgres]' --with codeocean python resolve_capsules.py
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from codeocean import CodeOcean

CACHE_PATH = Path("weekly_report.parquet")
OUT_PATH = Path("capsule_map.json")
RESULTS_BUCKET = "codeocean-s3resultsbucket-1182nktl2bh9f"
BATCH_BUCKET = "codeocean-s3batchbucket-16itpvq060udk"
COVER = 0.99  # resolve results-bucket capsules up to this cumulative share of size

client = CodeOcean(
    domain="https://codeocean.allenneuraldynamics.org",
    token=os.environ["CODE_OCEAN_API_KEY"],
)

df = pd.read_parquet(CACHE_PATH)
df["size_tb"] = df["size_in_bytes"] / 1e12

# All batch-bucket capsules (top-level prefix is the capsule id).
batch_caps = set(df.loc[df["bucket"] == BATCH_BUCKET, "prefix"].dropna().unique())

# Results-bucket capsules (second path segment) covering COVER of the bucket size.
res = df[df["bucket"] == RESULTS_BUCKET].copy()
res["cap"] = res["subprefix"].str.split("/").str[1]
per = res.groupby("cap")["size_tb"].sum().sort_values(ascending=False)
cum = per.cumsum() / per.sum()
res_caps = set(per.index[: (cum <= COVER).sum() + 1])

targets = sorted((batch_caps | res_caps) - {None})
print(f"resolving {len(targets)} capsule ids "
      f"({len(batch_caps)} batch + {len(res_caps)} results-99%)")


def resolve(cap_id):
    try:
        c = client.capsules.get_capsule(cap_id)
        return cap_id, {"name": c.name, "tags": list(getattr(c, "tags", None) or [])}
    except Exception:
        return cap_id, None  # 404 / deleted / inaccessible


mapping = {}
done = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    futures = [ex.submit(resolve, c) for c in targets]
    for fut in as_completed(futures):
        cap_id, info = fut.result()
        mapping[cap_id] = info
        done += 1
        if done % 200 == 0:
            print(f"  {done}/{len(targets)}")

resolved = sum(1 for v in mapping.values() if v)
OUT_PATH.write_text(json.dumps(mapping, indent=0))
print(f"resolved {resolved}/{len(targets)} -> {OUT_PATH}")
