# Out-of-scope: "Allen Insitute" funder-typo records (9)

Surfaced while searching DocDB for records with the same defects as
[aind-beh-ephys-analysis#12](https://github.com/AllenNeuralDynamics/aind-beh-ephys-analysis/issues/12).
**These are NOT fixable with the issue #12 rule set** and are documented here only
so they aren't re-discovered. They belong to the general v1→v2 upgrade effort.

## What they are

9 `ecephys` assets (2023, subjects 655019 / 661278 / 661279 / 662198 / 664484),
all present in v1 and **absent from v2**. They share one defect with the #12 set
— a `funding_source.funder` stored as a bare string — but the string is a
*different* typo: `"Allen Insitute for Neural Dynamics"` (missing the second "t"
in "Institute"; should be AIND / Allen Institute for Neural Dynamics).

## Why they're out of scope

Fixing the funder is necessary but **not sufficient**. After the funder is
corrected, the upgrade hits a second, harder blocker in `procedures`:

```
Unsupported craniotomy_type: None. Expected one of ['Dual hemisphere craniotomy', ...]
```

A `Craniotomy` procedure has `craniotomy_type = None`, and v2 requires a value
from a fixed enum. Unlike the #12 fixes (which backfill a known value — a
timestamp, the subject id, a known funder), choosing the correct
`craniotomy_type` requires surgical/domain knowledge we don't have. So these
cannot be repaired mechanically with the same rules.

## The 9 records

```
ecephys_655019_2023-03-17_15-49-02
ecephys_655019_2023-03-17_15-49-02_nwb_2023-05-16_16-11-23
ecephys_661278_2023-03-29_16-42-38
ecephys_In_2023-03-29_16-42-38_nwb_2023-05-16_16-06-12
ecephys_661279_2023-03-23_15-31-18
ecephys_661279_2023-03-23_15-31-18_nwb_2023-05-16_16-18-59
ecephys_662198_2023-04-20_14-31-20
ecephys_662198_2023-04-20_14-31-20_sorted-ks2.5_2023-05-16_20-29-06
ecephys_664484_2023-04-24_19-35-59
```

## Note

A much larger population (~2115 records) has `procedures.subject_id` missing and
is absent from v2, but a sample showed only ~8% upgrade after the #12 fixes — the
rest are blocked by unrelated, heterogeneous issues. Like the records above, they
are part of the general long-tail upgrade effort, not this targeted batch.
