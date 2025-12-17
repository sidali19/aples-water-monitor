import os
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

import numpy as np
import requests
from PIL import Image
from requests.adapters import HTTPAdapter, Retry




TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

CDSE_CRS = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
DEFAULT_DATASET = "sentinel-2-l2a"

EPS = 1e-6
DEFAULT_TIMEOUT = 60


log = logging.getLogger(__name__)


TRUE_COLOR_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B02", "B03", "B04"],
    output: { bands: 3, sampleType: "AUTO" }
  };
}
function evaluatePixel(s) {
  return [2.5 * s.B04, 2.5 * s.B03, 2.5 * s.B02];
}
"""

NDWI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B03", "B08"],
    output: { bands: 1, sampleType: "AUTO" }
  };
}
function evaluatePixel(s) {
  let ndwi = (s.B03 - s.B08) / (s.B03 + s.B08 + 1e-6);
  return [(ndwi + 1) / 2];
}
"""


@dataclass(frozen=True)
class CDSECredentials:
    client_id: str
    client_secret: str


def load_env_credentials() -> CDSECredentials:
    """Load credentials from environment variables."""
    client_id = os.environ.get("CDSE_CLIENT_ID") or os.environ.get("SH_CLIENT_ID")
    client_secret = os.environ.get("CDSE_CLIENT_SECRET") or os.environ.get("SH_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "CDSE_CLIENT_ID / CDSE_CLIENT_SECRET (or SH_CLIENT_ID / SH_CLIENT_SECRET) missing."
        )

    return CDSECredentials(client_id=client_id, client_secret=client_secret)


class CDSEClient:
    """
    A client to interact with CDSE Process API
    - Handles authentication
    - Retries on transient failures
    """

    def __init__(self, credentials: CDSECredentials):
        self.credentials = credentials
        self.token: Optional[str] = None

        retry_strategy = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.session = requests.Session()
        self.session.mount("https://", adapter)


    def authenticate(self) -> str:
        log.info("Authenticating with CDSE...")

        resp = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            },
            timeout=DEFAULT_TIMEOUT,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Authentication failed [{resp.status_code}]: {resp.text}"
            )

        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError("Missing 'access_token' in authentication response.")

        self.token = token
        return token


    def run_process(self, body: Dict[str, Any]) -> bytes:
        """Call CDSE Process API"""
        if not self.token:
            self.authenticate()

        log.debug("Sending Process API request...")

        resp = self.session.post(
            PROCESS_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "image/png",
            },
            timeout=DEFAULT_TIMEOUT,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Process API error [{resp.status_code}]: {resp.text}"
            )

        return resp.content


def build_body(
    bbox: Tuple[float, float, float, float],
    time_range: Tuple[str, str],
    width: int,
    height: int,
    evalscript: str,
) -> Dict[str, Any]:

    min_lon, min_lat, max_lon, max_lat = bbox

    return {
        "input": {
            "bounds": {
                "properties": {"crs": CDSE_CRS},
                "bbox": [min_lon, min_lat, max_lon, max_lat],
            },
            "data": [{
                "type": DEFAULT_DATASET,
                "dataFilter": {"timeRange": {"from": time_range[0], "to": time_range[1]}},
            }],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/png"},
            }],
        },
        "evalscript": evalscript,
    }


def load_png_array(data: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(data)))


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def fetch_true_color(
    client: CDSEClient,
    bbox: Tuple[float, float, float, float],
    time_range: Tuple[str, str],
    size: Tuple[int, int] = (512, 512),
    out_dir: str = "data",
) -> Path:

    body = build_body(bbox, time_range, size[0], size[1], TRUE_COLOR_EVALSCRIPT)
    array = load_png_array(client.run_process(body))

    out_path = ensure_dir(out_dir) / f"true_color_{timestamp()}.png"
    Image.fromarray(array).save(out_path)

    return out_path


def fetch_ndwi(
    client: CDSEClient,
    bbox: Tuple[float, float, float, float],
    time_range: Tuple[str, str],
    size: Tuple[int, int] = (512, 512),
    out_dir: str = "data",
):
    body = build_body(bbox, time_range, size[0], size[1], NDWI_EVALSCRIPT)
    raw_uint8 = load_png_array(client.run_process(body))

    out = ensure_dir(out_dir)
    raw_path = out / f"ndwi_raw_{timestamp()}.png"

    Image.fromarray(raw_uint8).save(raw_path)

    return raw_path
