import datetime as dt
from pathlib import Path
import csv

from alpes_water_monitor.config.fields import default_st_cassien_config
from alpes_water_monitor.services.field_metrics import run_daily_ndwi_for_fields


def daterange(start: dt.date, end: dt.date):
    """Yield all dates from start to end inclusive."""
    cur = start
    one_day = dt.timedelta(days=1)
    while cur <= end:
        yield cur
        cur += one_day


def main():
    start_date = dt.date(2024, 4, 1)
    end_date = dt.date(2024, 7, 31)

    field_cfg = default_st_cassien_config()

    out_dir = Path("data") / "field_ndwi_timeseries_local"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "st_cassien_ndwi_timeseries.csv"

    fieldnames = [
        "date",
        "field_id",
        "field_name",
        "mean_ndwi",
        "water_fraction_pos",
        "water_fraction_strong",
    ]

    print(f"Writing time series to {out_path} ...")

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for current_date in daterange(start_date, end_date):
            print(f"\n=== {current_date} ===")
            try:
                daily_rows = run_daily_ndwi_for_fields(
                    date=current_date,
                    field_config=field_cfg,
                )
            except Exception as e:
                print(f"  Error on {current_date}: {e}")
                continue

            if not daily_rows:
                print("  No active fields (before monitoring_start or no pixels).")
                continue

            for row in daily_rows:
                writer.writerow(row)
                print(
                    f"  {row['field_id']}: mean_ndwi={row['mean_ndwi']:.3f}, "
                    f"water_fraction_pos={row['water_fraction_pos']:.3f}, "
                    f"water_fraction_strong={row['water_fraction_strong']:.3f}"
                )

    print(f"\n Time series saved to {out_path}")


if __name__ == "__main__":
    main()
