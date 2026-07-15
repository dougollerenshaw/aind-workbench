"""Summarize S3 data usage by project and by modality from the storage-lens weekly_report table.

Run with:
    AWS_PROFILE=aind_prod_sso AWS_DEFAULT_REGION=us-west-2 \
        uv run --with 'awswrangler[postgres]' python summarize_usage.py
"""

import awswrangler as wr
import pandas as pd

SECRET_NAME = "/aind/prod/rds/storage-lens-metrics/credentials/readonly"

BY_PROJECT_SQL = """
SELECT
    COALESCE(project_name, '(no project)') AS project_name,
    SUM(size_in_bytes) / 1e12 AS total_tb,
    SUM(number_of_files) AS total_files,
    COUNT(DISTINCT prefix) AS n_prefixes
FROM weekly_report
GROUP BY COALESCE(project_name, '(no project)')
ORDER BY total_tb DESC
"""

BY_BUCKET_SQL = """
SELECT
    bucket,
    SUM(size_in_bytes) / 1e12 AS total_tb,
    SUM(number_of_files) AS total_files
FROM weekly_report
GROUP BY bucket
ORDER BY total_tb DESC
"""

# Asset names in the open-data bucket follow "<modality>_<subject>_<date>_...",
# so the token before the first underscore approximates the modality/platform.
BY_MODALITY_SQL = """
SELECT
    split_part(prefix, '_', 1) AS modality,
    SUM(size_in_bytes) / 1e12 AS total_tb,
    SUM(number_of_files) AS total_files,
    COUNT(DISTINCT prefix) AS n_prefixes
FROM weekly_report
WHERE prefix ~ '^[a-zA-Z]'
GROUP BY split_part(prefix, '_', 1)
ORDER BY total_tb DESC
LIMIT 25
"""

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 100)
pd.options.display.float_format = "{:,.2f}".format

with wr.postgresql.connect(secret_id=SECRET_NAME) as con:
    by_project = wr.postgresql.read_sql_query(BY_PROJECT_SQL, con=con)
    by_bucket = wr.postgresql.read_sql_query(BY_BUCKET_SQL, con=con)
    by_modality = wr.postgresql.read_sql_query(BY_MODALITY_SQL, con=con)

print("=== Total size by bucket (TB) ===")
print(by_bucket.to_string(index=False))
print()
print("=== Top projects by total size (TB) ===")
print(by_project.head(30).to_string(index=False))
print()
print("=== Named prefixes by leading token, approx modality/platform (TB) ===")
print(by_modality.to_string(index=False))
