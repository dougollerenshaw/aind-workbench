import awswrangler as wr

secret_name = "/aind/prod/rds/storage-lens-metrics/credentials/readonly"
table_name = "weekly_report"

with wr.postgresql.connect(secret_id=secret_name) as con:
    df = wr.postgresql.read_sql_table(
        table=table_name,
        con=con
    )

print(df.head())