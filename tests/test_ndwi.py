import datetime as dt
from pathlib import Path

import numpy as np
import shapely.geometry as geom
import pytest

from alpes_water_monitor.utils import ndwi
from alpes_water_monitor.utils.models import Field, FieldConfig
from alpes_water_monitor.services.field_metrics import compute_field_metrics_from_ndwi, MetricsConfig


def test_build_time_interval():
    day = dt.date(2024, 4, 10)
    start, end = ndwi.build_time_interval(day, window_days=3)
    assert start == "2024-04-07T00:00:00Z"
    assert end == "2024-04-13T23:59:59Z"


def test_compute_water_metrics():
    arr = np.array([[0.5, -0.5], [0.0, 0.25]])
    metrics = ndwi.compute_water_metrics(arr, threshold=0.0)
    assert metrics["mean_ndwi"] == float(np.mean(arr))
    assert metrics["water_fraction"] == float(np.mean(arr > 0.0))
    assert metrics["ndwi_min"] == float(np.min(arr))
    assert metrics["ndwi_max"] == float(np.max(arr))


def test_fetch_ndwi_for_bbox_monkeypatched(monkeypatch, tmp_path):
    fake_array = np.ones((1, 1), dtype=np.float32) * 0.75  # [0,1] from fetch_ndwi

    class DummyClient:
        def __init__(self, creds):
            self.creds = creds

    def fake_load_env_credentials():
        return {"client_id": "x", "client_secret": "y"}

    def fake_fetch_ndwi(_client, bbox, time_range, size, out_dir):
        assert bbox == (1, 2, 3, 4)
        assert time_range[0].startswith("2024-04-09")
        assert size == (2, 2)
        assert out_dir == str(tmp_path)
        return Path("raw.png")

    monkeypatch.setattr(ndwi, "load_env_credentials", fake_load_env_credentials)
    monkeypatch.setattr(ndwi, "CDSEClient", DummyClient)
    monkeypatch.setattr(ndwi, "fetch_ndwi", fake_fetch_ndwi)

    cfg = ndwi.NDWIConfig(width=2, height=2, window_days=1, out_dir=tmp_path)
    raw_path = ndwi.fetch_ndwi_for_bbox((1, 2, 3, 4), dt.date(2024, 4, 10), cfg)

    assert raw_path == Path("raw.png")


def test_compute_field_metrics_from_ndwi():
    ndwi_real = np.full((2, 2), 0.6, dtype=float)

    field = Field(
        id="f1",
        name="Test Field",
        polygon=geom.box(0.0, 0.0, 1.0, 1.0),
        monitoring_start=dt.date(2024, 4, 1),
    )

    cfg = FieldConfig(
        location_id="loc1",
        location_name="Test Location",
        bbox=(0.0, 0.0, 2.0, 2.0),
        fields=[field],
    )

    results = compute_field_metrics_from_ndwi(
        ndwi_real,
        cfg,
        dt.date(2024, 4, 10),
        MetricsConfig(),
    )

    assert len(results) == 1
    rec = results[0]
    assert rec["field_id"] == "f1"
    assert rec["mean_ndwi"] == pytest.approx(0.6)
    assert rec["water_fraction_pos"] == pytest.approx(1.0)
    assert rec["water_fraction_strong"] == pytest.approx(1.0)
