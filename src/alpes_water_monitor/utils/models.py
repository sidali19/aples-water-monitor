from dataclasses import dataclass
from typing import Tuple, List
from datetime import date
from shapely.geometry import Polygon


BBox = Tuple[float, float, float, float] # (min_lon, min_lat, max_lon, max_lat)

@dataclass
class Location:
    id: str
    name: str
    type: str           # lake / river ...
    bbox: BBox
    monitoring_start: date

@dataclass
class Field:
    id: str
    name: str
    polygon: Polygon
    monitoring_start: date   

@dataclass
class FieldConfig:
    location_id: str
    location_name: str    
    bbox: BBox
    fields: List[Field]
