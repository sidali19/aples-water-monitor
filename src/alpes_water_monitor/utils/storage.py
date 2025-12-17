from __future__ import annotations
from pathlib import Path
from typing import Optional
import os
import tempfile

from dagster import AssetExecutionContext
from minio import Minio
import numpy as np
from PIL import Image
import pandas as pd


def get_minio_client() -> Optional[Minio]:
    endpoint = os.getenv("ALPES_MINIO_ENDPOINT")
    if not endpoint:
        return None

    secure = False
    if endpoint.startswith("http://"):
        endpoint = endpoint[len("http://") :]
        secure = False
    elif endpoint.startswith("https://"):
        endpoint = endpoint[len("https://") :]
        secure = True

    access_key = os.getenv("ALPES_MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("ALPES_MINIO_SECRET_KEY", "minioadmin")

    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def upload_file_to_minio(context: AssetExecutionContext, local_path: Path, object_name: str):
    client = get_minio_client()
    if client is None:
        raise RuntimeError(f"[minio] endpoint not set, cannot upload {local_path}")

    bucket_name = os.getenv("ALPES_MINIO_BUCKET", "alpes-water-monitor")

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    client.fput_object(
        bucket_name=bucket_name,
        object_name=object_name,
        file_path=str(local_path),
    )
    context.log.info("[minio] Uploaded %s to s3://%s/%s", local_path, bucket_name, object_name)
    return f"s3://{bucket_name}/{object_name}"


def download_file_from_minio(
    context: AssetExecutionContext,
    object_name: str,
    dest_path: Path,
    bucket_name: str | None = None,
) -> Optional[Path]:
    client = get_minio_client()
    if client is None:
        context.log.warning("[minio] endpoint not set, cannot download %s", object_name)
        return None

    bucket_name = bucket_name or os.getenv("ALPES_MINIO_BUCKET", "alpes-water-monitor")

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        client.fget_object(bucket_name=bucket_name, object_name=object_name, file_path=str(dest_path))
        context.log.info("[minio] Downloaded s3://%s/%s to %s", bucket_name, object_name, dest_path)
        return dest_path
    except Exception as e:
        context.log.warning("[minio] Failed to download s3://%s/%s: %s", bucket_name, object_name, e)
        return None


def load_ndwi_from_path(
    context: AssetExecutionContext,
    path_or_object: str,
) -> np.ndarray:
    """
    Load NDWI PNG from local path or s3://bucket/object and return float32 array in [-1,1].
    """
    if path_or_object.startswith("s3://"):
        _, _, rest = path_or_object.partition("s3://")
        bucket_and_key = rest.split("/", 1)
        if len(bucket_and_key) != 2:
            raise ValueError(f"Invalid s3 URI: {path_or_object}")
        bucket_name, object_name = bucket_and_key
        tmp = Path(tempfile.mkdtemp()) / "ndwi.png"
        downloaded = download_file_from_minio(context, object_name, tmp, bucket_name=bucket_name)
        if downloaded is None:
            raise FileNotFoundError(f"Failed to download {path_or_object}")
        local_path = downloaded
    else:
        local_path = Path(path_or_object)

    if not local_path.exists():
        raise FileNotFoundError(f"NDWI file not found at {local_path}")

    img = Image.open(local_path)
    if img.mode != "L":
        img = img.convert("L")
    arr = np.array(img, dtype=np.float32) / 255.0
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D NDWI array, got shape {arr.shape}")
    ndwi_real = arr * 2.0 - 1.0
    return ndwi_real.astype(np.float32)


def read_csv_from_s3_uri(context: AssetExecutionContext, s3_uri: str) -> pd.DataFrame:
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got {s3_uri}")
    _, _, rest = s3_uri.partition("s3://")
    parts = rest.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid s3 URI: {s3_uri}")
    bucket_name, object_name = parts
    tmp = Path(tempfile.mkdtemp()) / "tmp.csv"
    downloaded = download_file_from_minio(context, object_name, tmp, bucket_name=bucket_name)
    if downloaded is None:
        raise FileNotFoundError(f"Failed to download {s3_uri}")
    return pd.read_csv(downloaded)


def write_df_to_minio_csv(
    context: AssetExecutionContext,
    df: pd.DataFrame,
    object_name: str,
) -> str:
    tmp = Path(tempfile.mkdtemp()) / "tmp.csv"
    df.to_csv(tmp, index=False)
    return upload_file_to_minio(context, tmp, object_name)
