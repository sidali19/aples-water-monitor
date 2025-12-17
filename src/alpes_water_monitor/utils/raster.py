from __future__ import annotations
from typing import Tuple
import numpy as np
from rasterio.transform import Affine
from rasterio.features import rasterize
from alpes_water_monitor.utils.models import Field, BBox


def bbox_to_affine(bbox: BBox, width: int, height: int) -> Affine:
    minx, miny, maxx, maxy = bbox
    pixel_width = (maxx - minx) / width
    pixel_height = (maxy - miny) / height  # top-down orientation
    return Affine(pixel_width, 0.0, minx, 0.0, -pixel_height, maxy)


def rasterize_field_mask(
    field: Field,
    bbox: BBox,
    width: int,
    height: int,
    *,
    all_touched: bool = True,
) -> np.ndarray:
    transform = bbox_to_affine(bbox, width, height)
    mask = rasterize(
        [(field.polygon, 1)],
        out_shape=(height, width),
        transform=transform,
        fill=0,
        all_touched=all_touched,
        dtype="uint8",
    )
    return mask.astype(bool)
