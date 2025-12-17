import datetime as dt
import os
from pprint import pprint

from alpes_water_monitor.config.fields import load_field_config_from_env
from alpes_water_monitor.utils.storage import load_ndwi_from_path
from alpes_water_monitor.services.field_metrics import (
    run_daily_ndwi_for_fields,
    compute_field_metrics_from_ndwi,
)


def main():
    date = dt.date(2024, 7, 10)
    cfg = load_field_config_from_env()

    print(f"Running daily NDWI pipeline for fields on {date}...")
    raw_path = run_daily_ndwi_for_fields(date=date, field_config=cfg)
    ndwi_real = load_ndwi_from_path(None, raw_path)
    results = compute_field_metrics_from_ndwi(ndwi_real, cfg, date)

    for row in results:
        pprint(row)


if __name__ == "__main__":
    main()
