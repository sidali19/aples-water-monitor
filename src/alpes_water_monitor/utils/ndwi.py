from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Dict
import datetime as dt
import logging
import numpy as np

from alpes_water_monitor.utils.cdse_client import load_env_credentials, CDSEClient, fetch_ndwi
from alpes_water_monitor.utils.models import BBox

logger = logging.getLogger(__name__)

@dataclass
class NDWIConfig:
    width: int = 512
    height: int = 512
    window_days: int = 5
    out_dir: Path = Path("data")
    file_prefix: str = "ndwi"

def build_time_interval(date: dt.date, window_days: int) -> Tuple[str, str]:
    start = (date - dt.timedelta(days=window_days)).isoformat() + "T00:00:00Z"
    end = (date + dt.timedelta(days=window_days)).isoformat() + "T23:59:59Z"
    return start, end

def fetch_ndwi_for_bbox(bbox: BBox, date: dt.date, config: NDWIConfig) -> Path:
    creds = load_env_credentials()
    client = CDSEClient(creds)
    time_interval = build_time_interval(date, config.window_days)
    raw_path = fetch_ndwi(
        client,
        bbox=bbox,
        time_range=time_interval,
        size=(config.width, config.height),
        out_dir=str(config.out_dir),
    )
    return raw_path

def compute_water_metrics(ndwi_array: np.ndarray, threshold: float = 0.0) -> Dict[str, float]:
    mean_ndwi = float(np.mean(ndwi_array))
    water_fraction = float(np.mean(ndwi_array > threshold))
    ndwi_min = float(np.min(ndwi_array))
    ndwi_max = float(np.max(ndwi_array))
    logger.debug("NDWI stats: min=%.3f max=%.3f mean=%.3f", ndwi_min, ndwi_max, mean_ndwi)
    return {
        "mean_ndwi": mean_ndwi,
        "water_fraction": water_fraction,
        "ndwi_min": ndwi_min,
        "ndwi_max": ndwi_max,
    }
