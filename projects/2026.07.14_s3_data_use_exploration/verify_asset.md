# Verify asset in S3

Asset: `exaSPIM_784896_2025-08-19_10-48-12_processed_2025-08-26_12-28-02`
Reported: bucket `aind-open-data`, 63,163,312,628,843 bytes (63.163 TB), 20,292,849 objects (Storage Lens snapshot 2026-06-28).

## 1. Refresh AWS login (token expires)

```bash
aws sso login --profile aind_prod_sso
```

## 2. Quick existence check (instant, non-recursive)

```bash
aws s3 ls "s3://aind-open-data/exaSPIM_784896_2025-08-19_10-48-12_processed_2025-08-26_12-28-02/" --profile aind_prod_sso
```

Confirms the asset exists in `aind-open-data` and shows its top-level contents.

## 3. Authoritative total size (matches the reported number to the byte)

```bash
aws s3 ls "s3://aind-open-data/exaSPIM_784896_2025-08-19_10-48-12_processed_2025-08-26_12-28-02/" --recursive --summarize --profile aind_prod_sso | tail -2
```

Expected output:

```
Total Objects: 20292849
Total Size: 63163312628843
```

`63163312628843` bytes = 63.163 TB.

## Notes

- Command #3 is slow: the asset is ~20.3 million objects, so the recursive listing makes tens of thousands of API calls and can take several minutes. That is normal, not a hang.
- Do not add `--human-readable`. With it the AWS CLI prints binary units (TiB), so you would see ~57.4 TiB and think it disagrees. Without it you get raw bytes, which match `63163312628843` exactly. (63.163 TB decimal = 57.4 TiB binary, same bytes.)
- Live S3 today may differ slightly from the reported number if objects were added or deleted since the 2026-06-28 Storage Lens snapshot. Small differences are snapshot drift, not an error; cite the snapshot date.
