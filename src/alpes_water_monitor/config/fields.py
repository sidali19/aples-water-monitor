from __future__ import annotations
from pathlib import Path
from typing import List
import json
import datetime as dt
import logging
from functools import lru_cache
import os

from shapely.geometry import shape, Polygon
from alpes_water_monitor.utils.models import Field, FieldConfig, BBox

logger = logging.getLogger(__name__)

def load_field_config(geojson_path: Path) -> FieldConfig:
    if not geojson_path.exists():
        raise FileNotFoundError(geojson_path)

    with geojson_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)

    props = gj.get("properties", {})

    location_id = props.get("location_id", geojson_path.stem)
    location_name = props.get("location_name", location_id)

    bbox_list = props.get("bbox")
    if not bbox_list or len(bbox_list) != 4:
        raise ValueError("Invalid bbox")

    bbox: BBox = tuple(float(v) for v in bbox_list)

    fields: List[Field] = []
    for feat in gj.get("features", []):
        fprops = feat.get("properties", {})
        geom = feat.get("geometry")
        if not geom:
            continue

        poly = shape(geom)
        if not isinstance(poly, Polygon):
            raise ValueError("Geometry must be Polygon")

        field_id = fprops.get("field_id")
        if not field_id:
            raise ValueError("Missing field_id")

        name = fprops.get("name", field_id)

        monitoring_str = fprops.get("monitoring_start")
        if not monitoring_str:
            raise ValueError(f"Missing monitoring_start for field {field_id}")
        monitoring_start = dt.date.fromisoformat(monitoring_str)


        fields.append(
            Field(
                id=field_id,
                name=name,
                polygon=poly,
                monitoring_start=monitoring_start,
            )
        )

    return FieldConfig(
        location_id=location_id,
        location_name=location_name,
        bbox=bbox,
        fields=fields,
    )

def load_field_config_from_env(env_var: str = "ALPES_FIELDS_CONFIG") -> FieldConfig:
    path_val = os.getenv(env_var)
    if not path_val:
        raise EnvironmentError(env_var)
    return load_field_config(Path(path_val))

@lru_cache(maxsize=1)
def default_st_cassien_config() -> FieldConfig:
    path = Path(__file__).resolve().parents[3] / "etc" / "fields_st_cassien.geojson"
    return load_field_config(path)
