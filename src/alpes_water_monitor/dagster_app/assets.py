import os
import datetime as dt
import pandas as pd
from dagster import (
    asset,
    DailyPartitionsDefinition,
    AssetExecutionContext,
    Output,
    AssetIn,
)

from alpes_water_monitor.config.fields import default_st_cassien_config
from alpes_water_monitor.utils.ndwi import NDWIConfig, fetch_ndwi_for_bbox
from alpes_water_monitor.utils.storage import (
    upload_file_to_minio,
    load_ndwi_from_path,
    read_csv_from_s3_uri,
    write_df_to_minio_csv,
)
from alpes_water_monitor.services.field_metrics import (
    compute_field_metrics_from_ndwi,
    compute_deltas,
    summarize_today_and_delta,
    MetricsConfig,
)

field_ndwi_partitions = DailyPartitionsDefinition(start_date="2024-04-01")


@asset(
    name="raw_ndwi_daily",
    partitions_def=field_ndwi_partitions,
    description=(
        "Fetch NDWI from CDSE for the Saint-Cassien bbox and store the raw PNG "
        "in MinIO/S3 for downstream processing."
    ),
)
def raw_ndwi_daily(context: AssetExecutionContext) -> Output[str]:
    target_date = dt.date.fromisoformat(context.partition_key)
    field_cfg = default_st_cassien_config()

    context.log.info(f"[raw_ndwi_daily] Fetching NDWI for {target_date}")

    raw_path = fetch_ndwi_for_bbox(
        bbox=field_cfg.bbox,
        date=target_date,
        config=NDWIConfig(),
    )

    object_name = f"raw_ndwi/date={target_date.isoformat()}/ndwi.png"
    s3_uri = upload_file_to_minio(context, raw_path, object_name)

    metadata = {
        "date": target_date.isoformat(),
        "minio_object": object_name,
        "s3_uri": s3_uri,
    }

    return Output(s3_uri, metadata=metadata)


@asset(
    name="field_ndwi_daily",
    partitions_def=field_ndwi_partitions,
    ins={"raw_ndwi_path": AssetIn("raw_ndwi_daily")},
    description=(
        "Daily NDWI metrics per field inside the Saint-Cassien bbox. "
        "Reads NDWI from S3/MinIO and writes one CSV per date. "
        "One row per field polygon."
    ),
)
def field_ndwi_daily(context: AssetExecutionContext, raw_ndwi_path: str) -> Output[str]:
    target_date = dt.date.fromisoformat(context.partition_key)

    context.log.info(f"[field_ndwi_daily] Running for date {target_date}")

    field_cfg = default_st_cassien_config()

    ndwi_real = load_ndwi_from_path(context, raw_ndwi_path)
    results = compute_field_metrics_from_ndwi(ndwi_real, field_cfg, target_date, MetricsConfig())

    if not results:
        context.log.warning("No active fields for this date (maybe before monitoring_start).")

    df = pd.DataFrame(results)
    object_name = f"field_ndwi_daily/date={target_date.isoformat()}/metrics.csv"
    s3_uri = write_df_to_minio_csv(context, df, object_name)

    context.log.info(f"[field_ndwi_daily] Wrote {len(df)} rows to {s3_uri}")

    metadata = {
        "rows": int(len(df)),
        "date": target_date.isoformat(),
        "minio_object": object_name,
        "s3_uri": s3_uri,
    }

    return Output(s3_uri, metadata=metadata)


@asset(
    name="field_ndwi_daily_delta",
    partitions_def=field_ndwi_partitions,
    ins={"today_path": AssetIn("field_ndwi_daily")},
    description=(
        "Per-field change in NDWI metrics between today and yesterday "
        "based on the per-partition CSVs from field_ndwi_daily."
    ),
)
def field_ndwi_daily_delta(context: AssetExecutionContext, today_path: str) -> Output[str]:
    target_date = dt.date.fromisoformat(context.partition_key)

    yesterday_date = target_date - dt.timedelta(days=1)
    bucket_name = os.getenv("ALPES_MINIO_BUCKET", "alpes-water-monitor")
    yesterday_object = f"field_ndwi_daily/date={yesterday_date.isoformat()}/metrics.csv"
    yesterday_s3 = f"s3://{bucket_name}/{yesterday_object}"

    context.log.info(
        f"[field_ndwi_daily_delta] Computing deltas for {target_date} "
        f"(today={today_path}, yesterday_s3={yesterday_s3})"
    )

    df_today = read_csv_from_s3_uri(context, today_path)

    try:
        df_yest = read_csv_from_s3_uri(context, yesterday_s3)
    except FileNotFoundError:
        context.log.warning(
            "[field_ndwi_daily_delta] Yesterday CSV missing in MinIO (%s); returning empty delta.",
            yesterday_s3,
        )
        merged = pd.DataFrame(
            columns=[
                "field_id",
                "field_name",
                "delta_mean_ndwi",
                "delta_water_fraction_pos",
                "delta_water_fraction_strong",
            ]
        )
    else:
        merged = compute_deltas(df_today, df_yest)
        if merged.empty:
            context.log.warning(
                "[field_ndwi_daily_delta] Merged dataframe is empty, no overlapping fields?"
            )

    object_name = f"field_ndwi_daily_delta/date={target_date.isoformat()}/metrics_delta.csv"
    s3_uri = write_df_to_minio_csv(context, merged, object_name)

    context.log.info(f"[field_ndwi_daily_delta] Wrote {len(merged)} rows with deltas to {s3_uri}")

    metadata = {
        "rows": int(len(merged)),
        "date": target_date.isoformat(),
        "yesterday_date": yesterday_date.isoformat(),
        "minio_object": object_name,
        "s3_uri": s3_uri,
    }

    return Output(s3_uri, metadata=metadata)


@asset(
    name="st_cassien_daily_summary",
    partitions_def=field_ndwi_partitions,
    ins={
        "field_ndwi_daily_path": AssetIn("field_ndwi_daily"),
        "field_ndwi_daily_delta_path": AssetIn("field_ndwi_daily_delta"),
    },
    description=(
        "Daily summary over all Saint-Cassien fields: number of active fields, "
        "average NDWI, average NDWI delta, etc."
    ),
)
def st_cassien_daily_summary(
    context: AssetExecutionContext,
    field_ndwi_daily_path: str,
    field_ndwi_daily_delta_path: str,
) -> Output[str]:
    target_date = dt.date.fromisoformat(context.partition_key)
    field_cfg = default_st_cassien_config()

    context.log.info(f"[st_cassien_daily_summary] Building summary for {target_date}")

    df_today = read_csv_from_s3_uri(context, field_ndwi_daily_path)

    try:
        df_delta = read_csv_from_s3_uri(context, field_ndwi_daily_delta_path)
    except FileNotFoundError:
        context.log.warning(
            f"[st_cassien_daily_summary] Delta file not found at {field_ndwi_daily_delta_path}, using empty dataframe."
        )
        df_delta = pd.DataFrame(
            columns=[
                "field_id",
                "field_name",
                "delta_mean_ndwi",
                "delta_water_fraction_pos",
                "delta_water_fraction_strong",
            ]
        )

    summary_rows = summarize_today_and_delta(df_today, df_delta, target_date, field_cfg)
    summary_df = pd.DataFrame(summary_rows)

    object_name = f"st_cassien_daily_summary/date={target_date.isoformat()}/summary.csv"
    s3_uri = write_df_to_minio_csv(context, summary_df, object_name)

    context.log.info(f"[st_cassien_daily_summary] Wrote {len(summary_df)} summary row(s) to {s3_uri}")

    metadata = {
        "rows": int(len(summary_df)),
        "date": target_date.isoformat(),
        "minio_object": object_name,
        "s3_uri": s3_uri,
    }

    return Output(s3_uri, metadata=metadata)
