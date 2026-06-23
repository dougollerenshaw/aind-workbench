# Mouse → IACUC protocol backfill (Dataverse)

One-time backfill of **`aibs_dim_mice.aibs_iacuc_protocol`** in Dataverse. Each mouse's
protocol is sourced from the AIND metadata pipeline (DocDB fast path, metadata-service
fallback) and written to Dataverse as a lookup. After this backfill, **Dataverse is the
source of truth** going forward, maintained by LAS / behavior / neurosurgery.

> This folder is **ephemeral** — it's a staging copy. The real home is a PR on
> [`AllenNeuralDynamics/aind-dataverse-migration-scripts`](https://github.com/AllenNeuralDynamics/aind-dataverse-migration-scripts).
> That's why the lookup logic is a **self-contained copy** here (`iacuc_lookup.py`) and
> does **not** import from the repo's `aind_workbench` package.

## Files
- **`iacuc_lookup.py`** — standalone two-stage lookup (DocDB → metadata-service),
  `get_iacuc_id_for_mouse(subject_id) -> "2414" | None`. No external-repo imports.
- **`backfill_iacuc_protocol.py`** — fetches mice from Dataverse, looks up each one's
  protocol, maps it to the Dataverse protocol GUID, and PATCHes the lookup.

## How it works
1. Auth to Dataverse (MSAL).
2. Fetch mice from `aibs_dim_mices` — by default only those whose `aibs_iacuc_protocol`
   is empty (the backfill target). `--overwrite` to also touch populated ones.
3. Build `{numeric protocol key → aibs_dim_iacuc_protocolsid GUID}` from
   `aibs_dim_iacuc_protocolses`. **Format mismatch:** Dataverse stores `"2414-Westlake"`
   while the lookup yields the bare `"2414"`, so we match on the leading digits.
4. For each mouse: `get_iacuc_id_for_mouse(subject_id)` → map number → GUID.
5. `PATCH /aibs_dim_mices(<guid>)` with `aibs_iacuc_protocol@odata.bind`.

## Safety — writes are off unless you ask twice
- **Dry-run is the default.** Writing needs the `--apply` flag **and** the env var
  `IACUC_BACKFILL_CONFIRM_WRITE=1`. With either missing, the write path raises — a bare
  `--apply` (or any accidental call) cannot write.
- PATCH uses `If-Match: *` (update-only; never creates a row).

## Usage
```bash
# Read-only dry runs (no writes possible):
uv run backfill_iacuc_protocol.py --subject-ids ids.json --no-fallback   # quick, targeted
uv run backfill_iacuc_protocol.py --top 50                               # first 50 empty-protocol mice
uv run backfill_iacuc_protocol.py                                        # full dry run

# Real write — ONLY after the migration-repo PR is approved:
IACUC_BACKFILL_CONFIRM_WRITE=1 uv run backfill_iacuc_protocol.py --apply
```
Flags: `--overwrite`, `--top N`, `--subject-ids <json array>`, `--no-fallback`,
`--env-file`, `--log-dir`. Env: the five `DATAVERSE_*` vars (auto-loaded from `.env`).

## Verified (2026-06-03, all read-only — nothing written)
- `iacuc_lookup.py` against live DocDB (`762287→2414`, `632269→2109`, `853578→2414`).
- Offline unit tests of `_numeric_key`, the protocol map, and `build_plan`
  (matched / skipped-existing / no-protocol / unmatched, incl. `--overwrite`).
- Write-gate: `--apply` without `IACUC_BACKFILL_CONFIRM_WRITE=1` refuses (exit 2).
- Full live **dry run** against Dataverse: auth + fetch 791 mice + map 17 protocols +
  per-mouse lookup + plan + dry-run output. `837468`/`841310` → `2414` PATCH plan; 0 writes.

## ⚠️ Confirm before the first real `--apply`
- **Target environment.** Verification ran against the sandbox org `orgc1997c24`, whose
  old subjects mostly aren't in (prod) DocDB, so match rates there are low and *not*
  representative. Point `DATAVERSE_HOST` at the **real target org** and pull from the
  matching DocDB; expect far higher coverage.
- **`@odata.bind` nav-property name** is assumed `aibs_iacuc_protocol` (matches
  `_aibs_iacuc_protocol_value`). A dry run can't confirm it — check `…/$metadata`, or do
  `--apply` on a single subject first. A wrong name → 400 on PATCH.
- **Fallback needs the internal host.** DocDB works anywhere; the metadata-service
  fallback needs VPN/DNS for `aind-metadata-service` (use `--no-fallback` otherwise).
