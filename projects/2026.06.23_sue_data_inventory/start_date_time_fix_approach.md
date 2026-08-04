# Revised approach: `start_date_time` / `end_date_time` for the broken compression process

This supersedes the "copy a timestamp from an adjacent process" guidance in
`migration_fix_spec.md` (Fix 1). That was wrong — the neighboring processes are
the *ephys* compression and a later *Fix Color Range* step, neither of which is
when the video compression ran.

## How the prior fix (PR #567) derived the times

[PR #567](https://github.com/AllenNeuralDynamics/aind-data-migration-scripts/pull/567):
- **`end_date_time`** = `LastModified` of the most recent `.mp4` under the asset's
  `behavior-videos/` S3 prefix (a real artifact timestamp).
- **`start_date_time`** = `end_date_time − 14h` (a stand-in; no real start signal exists).

## What we confirmed for our 19 records (read from S3)

S3 is reachable with the **`aind_dev_sso`** profile (it can read the prod bucket
`aind-private-data-prod-o5171v`; no prod profile needed). The compressed videos
are at `{location}/behavior-videos/<Camera>/video.mp4`.

Key findings — **this was not one run, so do NOT hardcode a single date:**

- The compressed `video.mp4` `LastModified` falls in **two batches**:
  **~2026-03-11/12** (13 records) and **~2026-04-06** (5 records). Even one subject
  (714116) is split across both.
- **3 of the 19 have no `behavior-videos/` mp4s** and need a fallback:
  `behavior_717121_2024-06-11_10-23-31`, `behavior_717121_2024-06-15_10-00-58`,
  `behavior_716325_2024-06-01_09-25-37`.

## Recommended approach

For each of the 19, target the data_process where `start_date_time is None`
(equivalently `code_url` contains `aind-behavior-video-transformation`) — by
content, not list index — and set:

- **`end_date_time`** = the latest `…/behavior-videos/**/video.mp4` `LastModified`
  for that record (per-record, like PR #567).
- **`start_date_time`** = `end_date_time − 14h` (matches PR #567) or `= end_date_time`
  if you'd rather not imply a duration. Either is fine; both are approximate.

**For the 3 records with no mp4:** fall back to a hardcoded plausible date (e.g.
`2026-03-12T00:00:00Z`, the dominant batch) with `start = end − 14h`, and note in
the process `notes` that the time is approximate. The goal is only a valid
datetime so the record upgrades (these fields are optional in v2).

## Reference: per-record latest mp4 timestamps already pulled

```
behavior_714116_2024-08-28_12-11-55   2026-03-12 01:32:02
behavior_714116_2024-08-29_11-46-43   2026-04-06 21:42:09
behavior_716325_2024-05-29_10-33-32   2026-04-06 21:40:07
behavior_716325_2024-05-30_11-33-46   2026-04-06 21:39:07
behavior_716325_2024-05-31_10-31-14   2026-04-06 21:44:44
behavior_716325_2024-06-01_09-25-37   (no mp4 — fallback)
behavior_717121_2024-06-11_10-23-31   (no mp4 — fallback)
behavior_717121_2024-06-15_10-00-58   (no mp4 — fallback)
behavior_717259_2024-06-28_11-17-19   2026-03-12 00:13:02
behavior_717263_2024-07-24_10-40-05   2026-03-12 00:48:45
behavior_722832_2024-09-13_11-55-58   2026-04-06 21:34:28
behavior_724172_2024-10-01_11-20-11   2026-03-12 00:02:07
behavior_724172_2024-10-03_11-02-53   2026-03-12 00:04:16
behavior_739970_2024-10-15_10-04-12   2026-03-12 00:03:22
behavior_739970_2024-10-16_12-15-24   2026-03-12 00:02:06
behavior_739977_2024-10-24_12-58-26   2026-03-11 23:54:40
behavior_751766_2025-02-13_11-31-21   2026-03-12 00:38:22
behavior_751766_2025-02-14_11-37-11   2026-03-12 00:42:06
behavior_751766_2025-02-15_12-08-11   2026-03-12 00:43:41
```

(Timestamps are the `video.mp4` write time = the most recent video processing for
that asset. The migration can re-list at run time or use these directly.)
