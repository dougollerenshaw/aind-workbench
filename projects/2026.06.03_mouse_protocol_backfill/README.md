# Mouse → IACUC protocol backfill (Dataverse)

Backfills the **`aibs_iacuc_protocol`** lookup on the Dataverse `aibs_dim_mice` table
from a CSV of `subject_id, iacuc_protocol_id` rows.

As of this writing the lookup is **null for all ~1156 mice** in `aibs_dim_mice`. The
column exists in the schema (a lookup → `aibs_dim_iacuc_protocols`, whose
`aibs_protocol_id` holds names like `2301-Westlake`), it just hasn't been populated.
This script populates it.

> **Who runs this:** someone with **write** access to Dataverse. The author of this
> folder does not have auth — this is meant to land via PR and be run by a credentialed
> operator after a dry-run review.

## Open questions — resolve before a real run

These are **unresolved** and intentionally deferred. The script is verified working
(auth + GUID resolution + dry-run plan all run end-to-end against a live org), but the
following need answers before an `--apply`:

1. **Which environment is the target?** During testing, two distinct Dataverse
   environments showed up and they do **not** hold the same data:

   | | `aind-metadata-service` proxy | direct Web API org `<sandbox-org>.crm.dynamics.com` |
   |---|---|---|
   | Mice | 1156 | 792 |
   | Mouse ID ranges | 83xxxx… | 61xxxx… (+ some 83xxxx) |
   | Protocols | 32, all `NNNN-Westlake` | 19, **including `TEST_IACUC_Protocol` / `TEST_IACUC_Archived_Protocol`** |

   The `TEST_IACUC_*` protocols + service account suggest the direct org is a
   **sandbox/dev** org, while the proxy reads from something prod-like. Confirm which org
   the backfill should actually write to, and set `DATAVERSE_HOST` to match. **Pull the
   ground-truth `subject_id → protocol_id` list from that same environment.**

2. **Sandbox protocol-population state is unknown.** The "null for all ~1156 mice"
   finding was observed via the **proxy** environment only. Whether the mice in
   the direct org (or whichever target you pick) already have protocols set has **not**
   been checked — verify with a dry run against the real target first.

3. **Sample CSV is environment-specific.** `sample_mouse_protocol.csv` uses IDs from the
   proxy environment; against the sandbox only some resolve (mice `839222`, `837468`,
   `841310`, `836174` and protocols `2403`, `2413`, `2414` exist there; mice `835272`,
   `830849` and protocols `2301`, `2307`, `2425` do not). Regenerate the fixture from the
   chosen target environment before relying on it.

4. **`@odata.bind` navigation-property name unverified** — see the "Verify before the
   first real `--apply`" section below.

## How it works

1. Read + validate the CSV (one protocol per mouse).
2. Resolve each `iacuc_protocol_id` → its GUID in `aibs_dim_iacuc_protocolses`.
3. Resolve each `subject_id` → its GUID in `aibs_dim_mices` (and read the current
   protocol value, so already-set mice are skipped by default).
4. `PATCH /aibs_dim_mices(<guid>)` binding the lookup via
   `"aibs_iacuc_protocol@odata.bind": "/aibs_dim_iacuc_protocolses(<guid>)"`.

It is **dry-run by default**: it resolves everything and logs the exact plan but writes
nothing. Add `--apply` to write. Each run also writes a timestamped `iacuc_backfill_*.log`.

## CSV format

```csv
subject_id,iacuc_protocol_id
835272,2301-Westlake
830849,2413-Westlake
```

`sample_mouse_protocol.csv` ships with this folder. **The pairings are simulated**, but
both the subject IDs and the protocol IDs are *real existing rows* in Dataverse, so GUID
resolution succeeds end-to-end during a test/dry run. Replace it with the real
`subject_id → protocol_id` ground-truth list (point `--csv` at your file, or overwrite
the sample). Column names are configurable via `--subject-col` / `--protocol-col`.

## Prerequisites

Set these environment variables (a `.env` file in this folder is auto-loaded — see
`.env.example`). These mirror `aind-dataverse-migration-scripts`:

| Variable | Purpose |
|---|---|
| `DATAVERSE_HOST` | e.g. `https://<org>.crm.dynamics.com` |
| `DATAVERSE_TENANT_ID` | Azure AD tenant id |
| `DATAVERSE_CLIENT_ID` | App registration (public client) id |
| `DATAVERSE_USERNAME` | Service/operator account (needs write on `aibs_dim_mice`) |
| `DATAVERSE_PASSWORD` | …its password |

## Run it (uv)

Dependencies are declared inline (PEP 723), so `uv run` installs them automatically.

```bash
# 1) Offline CSV sanity check — no network, no auth:
uv run backfill_iacuc_protocol.py --validate-only

# 2) Dry run against Dataverse (needs read auth) — REVIEW THE PLAN + any warnings:
uv run backfill_iacuc_protocol.py --csv sample_mouse_protocol.csv

# 3) Optional: limit to the first few rows while testing the write path:
uv run backfill_iacuc_protocol.py --csv sample_mouse_protocol.csv --apply --top 3

# 4) Full apply:
uv run backfill_iacuc_protocol.py --csv your_real_data.csv --apply
```

Useful flags: `--overwrite` (also update mice that already have a protocol),
`--top N` (cap rows), `--log-dir DIR`.

Non-uv fallback: `pip install -r requirements.txt` then `python backfill_iacuc_protocol.py ...`.

## Safety notes

- **Dry-run is the default.** Writing requires the explicit `--apply` flag.
- **Skip-existing by default.** Mice that already have a protocol are left untouched
  (and flagged if they differ from the CSV); pass `--overwrite` to replace them.
- **Update-only writes.** PATCH is sent with `If-Match: *`, so a mistyped GUID errors
  instead of silently creating an orphan record.
- **Pre-flight reporting.** Unmatched subject IDs and protocol IDs are listed before any
  write, so you can fix the CSV first.

## ⚠️ Verify before the first real `--apply`

The `@odata.bind` navigation-property name is set to **`aibs_iacuc_protocol`**
(`IACUC_PROTOCOL_NAV` in the script). This matches the lookup's value column
(`_aibs_iacuc_protocol_value`) and is almost certainly correct, but in Dataverse a
navigation property *can* differ from the attribute logical name. Confirm once against:

```
{DATAVERSE_HOST}/api/data/v9.2/$metadata
```

Find `EntityType Name="aibs_dim_mice"` → its `NavigationProperty` pointing at
`aibs_dim_iacuc_protocols`. A wrong name produces a `400` on PATCH (which the dry run
cannot detect, since dry run never PATCHes). The simplest live check is
`--apply --top 1` and confirm one row updates before running the rest.

## Provenance

Auth, querying, and lookup-binding follow the conventions in
[`AllenNeuralDynamics/aind-dataverse-migration-scripts`](https://github.com/AllenNeuralDynamics/aind-dataverse-migration-scripts).
That repo's load helpers only **create** rows (POST + skip-existing); they have no update
path. This backfill targets rows that already exist, so it adds the missing
**PATCH-by-GUID** step. If useful, this can be folded into that repo as an
`iacuc-protocol` table loader / an `update` mode on the shared utils.
