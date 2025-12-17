from __future__ import annotations
from typing import Dict, Any, List
import datetime as dt
from dataclasses import dataclass
import numpy as np
import pandas as pd

from alpes_water_monitor.utils.models import FieldConfig
from alpes_water_monitor.utils.raster import rasterize_field_mask
from alpes_water_monitor.utils.ndwi import NDWIConfig, fetch_ndwi_for_bbox
from alpes_water_monitor.utils.storage import load_ndwi_from_path

@dataclass
class MetricsConfig:
    water_threshold_pos: float = 0.0
    water_threshold_strong: float = 0.2
    all_touched: bool = True

def _compute_field_metrics(
    ndwi_real: np.ndarray,
    field_config: FieldConfig,
    date: dt.date,
    metrics_cfg: MetricsConfig,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    height, width = ndwi_real.shape

    for field in field_config.fields:
        if date < field.monitoring_start:
            continue

        mask = rasterize_field_mask(
            field,
            field_config.bbox,
            width,
            height,
            all_touched=metrics_cfg.all_touched,
        )

        values = ndwi_real[mask]
        if values.size == 0:
            continue

        results.append(
            {
                "date": date.isoformat(),
                "field_id": field.id,
                "field_name": field.name,
                "mean_ndwi": float(np.mean(values)),
                "water_fraction_pos": float(np.mean(values > metrics_cfg.water_threshold_pos)),
                "water_fraction_strong": float(np.mean(values > metrics_cfg.water_threshold_strong)),
            }
        )

    return results

def compute_field_metrics_from_ndwi(
    ndwi_real: np.ndarray,
    field_config: FieldConfig,
    date: dt.date,
    metrics_cfg: MetricsConfig | None = None,
) -> List[Dict[str, Any]]:
    return _compute_field_metrics(
        ndwi_real,
        field_config,
        date,
        metrics_cfg or MetricsConfig(),
    )

def compute_deltas(df_today: pd.DataFrame, df_yest: pd.DataFrame) -> pd.DataFrame:
    required = {"field_id", "field_name", "mean_ndwi", "water_fraction_pos", "water_fraction_strong"}
    missing_today = required - set(df_today.columns)
    missing_yest = required - set(df_yest.columns)

    if missing_today:
        raise ValueError(f"df_today missing columns: {sorted(missing_today)}")
    if missing_yest:
        raise ValueError(f"df_yest missing columns: {sorted(missing_yest)}")

    t = df_today.rename(
        columns={
            "field_name": "field_name_today",
            "mean_ndwi": "mean_ndwi_today",
            "water_fraction_pos": "water_fraction_pos_today",
            "water_fraction_strong": "water_fraction_strong_today",
        }
    )
    y = df_yest.rename(
        columns={
            "field_name": "field_name_yest",
            "mean_ndwi": "mean_ndwi_yest",
            "water_fraction_pos": "water_fraction_pos_yest",
            "water_fraction_strong": "water_fraction_strong_yest",
        }
    )

    merged = t.merge(
        y,
        on="field_id",
        how="inner",
        validate="one_to_one",
    )

    if merged.empty:
        return merged

    merged["field_name"] = merged["field_name_today"]

    merged["delta_mean_ndwi"] = merged["mean_ndwi_today"] - merged["mean_ndwi_yest"]
    merged["delta_water_fraction_pos"] = (
        merged["water_fraction_pos_today"] - merged["water_fraction_pos_yest"]
    )
    merged["delta_water_fraction_strong"] = (
        merged["water_fraction_strong_today"] - merged["water_fraction_strong_yest"]
    )

    cols = [
        "field_id",
        "field_name",
        "delta_mean_ndwi",
        "delta_water_fraction_pos",
        "delta_water_fraction_strong",
    ]
    return merged[cols]

def summarize_today_and_delta(
    df_today: pd.DataFrame,
    df_delta: pd.DataFrame,
    target_date: dt.date,
    field_config: FieldConfig,
):
    avg_delta = (
        float(df_delta["delta_mean_ndwi"].mean())
        if not df_delta.empty and "delta_mean_ndwi" in df_delta.columns
        else None
    )

    return [
        {
            "date": target_date.isoformat(),
            "location_id": field_config.location_id,
            "location_name": field_config.location_name,
            "total_fields": len(df_today),
            "avg_mean_ndwi": float(df_today["mean_ndwi"].mean()) if not df_today.empty else None,
            "avg_delta_mean_ndwi": avg_delta,
        }
    ]


def run_daily_ndwi_for_fields(
    date: dt.date,
    field_config: FieldConfig,
    metrics_cfg: MetricsConfig | None = None,
    ndwi_cfg: NDWIConfig | None = None,
):
    """
    Convenience helper used by local scripts:
      - fetch NDWI for the bbox (PNG path)
      - load/convert NDWI locally
      - compute per-field metrics
    """
    ndwi_cfg = ndwi_cfg or NDWIConfig()
    raw_path = fetch_ndwi_for_bbox(field_config.bbox, date, ndwi_cfg)
    ndwi_real = load_ndwi_from_path(None, raw_path)
    return compute_field_metrics_from_ndwi(ndwi_real, field_config, date, metrics_cfg)
