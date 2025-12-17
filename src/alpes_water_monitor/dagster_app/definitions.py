# src/alpes_water_monitor/dagster_app/definitions.py

import os
from dagster import Definitions, load_assets_from_modules, resource
from minio import Minio

from . import assets


@resource
def minio_client_resource(_):
    endpoint = os.getenv("ALPES_MINIO_ENDPOINT", "minio:9000")
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


defs = Definitions(
    assets=load_assets_from_modules([assets]),
    resources={
        "minio_client": minio_client_resource,
    },
)
