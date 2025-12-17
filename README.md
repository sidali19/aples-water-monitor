# Alpes Water Monitor

Dagster pipeline to monitor surface water over Alpes-Maritimes (Saint‑Cassien example). It:
- Fetches Sentinel‑2 NDWI from Copernicus Data Space Ecosystem (CDSE).
- Stores raw NDWI PNGs (human-friendly) in MinIO (S3-compatible).
- Computes daily per-field NDWI metrics, day-over-day deltas, and a daily summary.
- Exchanges data between assets via `s3://<bucket>/<key>` URIs in MinIO.

## NDWI & CDSE (context)
- **NDWI**: Normalized Difference Water Index. Higher → more water-like.
- **CDSE**: Copernicus Data Space Ecosystem (https://dataspace.copernicus.eu/). Create an account, register an app, and get `client_id` / `client_secret`.

## Entrypoint: geometry & config
- `etc/fields_st_cassien.geojson`: bounding box (fetch extent) + field polygons.
- `src/alpes_water_monitor/config/fields.py`: loads the GeoJSON into `FieldConfig` (used for fetch extent + mask rasterization).

## Code walkthrough (high level)
- `dagster_app/`: assets + definitions (orchestration only).
- `services/field_metrics.py`: domain logic (per-field metrics, deltas, summary) + `MetricsConfig` (thresholds, raster all_touched).
- `utils/`: CDSE client, NDWI fetch (returns raw PNG path), NDWI loader (PNG → grayscale → validated 2D → float32 NDWI for metrics), MinIO storage helpers, rasterization, models.
- `config/`: config loaders (GeoJSON fields config).
- `infra/`: Terraform for k3d deployment.
- `scripts/`: helper scripts (local runs, deploy).
- `tests/`: unit tests.

End-to-end flow:
1) `utils/ndwi.fetch_ndwi_for_bbox`: call CDSE, get raw NDWI PNG path.
2) `utils/storage.load_ndwi_from_path`: download if `s3://`, grayscale + 2D validation, scale for metrics.
3) `services/field_metrics.py`: rasterize masks (`utils/raster`), compute per-field metrics, compute deltas (merge on field_id), summarize.
4) `dagster_app/assets.py`: orchestrates fetch → metrics → delta → summary, reading/writing via MinIO using `s3://...` contracts.

## Data contracts (MinIO object keys)
- Raw NDWI PNG: `raw_ndwi/date=YYYY-MM-DD/ndwi.png`
- Per-field metrics: `field_ndwi_daily/date=YYYY-MM-DD/metrics.csv`
- Deltas: `field_ndwi_daily_delta/date=YYYY-MM-DD/metrics_delta.csv`
- Summary: `st_cassien_daily_summary/date=YYYY-MM-DD/summary.csv`

## Deployment architecture (k3d + Terraform)
- Namespace: `alpes-water-monitor`
- Deployments/Pods:
  - `minio` (Svc: `minio:9000/9001`; optional PVC)
  - `dagster-webserver` (Svc: `dagster-webserver:3000`)
  - `dagster-daemon`
  - `alpes-monitor-app` (user code + assets)
- Secrets: `cdse-credentials` (client_id/secret), MinIO creds via env.
- Flow: Dagster webserver/daemon call user-code over gRPC/HTTP; user-code reads/writes MinIO; assets exchange `s3://` URIs.

```mermaid
flowchart TB
    subgraph Namespace: alpes-water-monitor
        MINIO[Deployment: minio\nSvc: minio:9000/9001]
        DAGWEB[Deployment: dagster-webserver\nSvc: dagster-webserver:3000]
        DAGDAEMON[Deployment: dagster-daemon]
        USER[Deployment: alpes-monitor-app\n(user code + assets)]
        SEC[Secrets: cdse-credentials, minio creds]
        USER -->|S3 ops| MINIO
        DAGWEB -. gRPC/HTTP .- USER
        DAGDAEMON -. gRPC/HTTP .- USER
    end
```

## Deployment (k3d + Terraform)
- Preferred: `scripts/deploy_k3d_tf.sh`  
  Builds the user-code image, imports it into k3d, and runs `terraform -chdir=infra apply` to create namespace, MinIO, Dagster webserver/daemon, and user-code deployment. Set `CDSE_CLIENT_ID/SECRET` and MinIO envs before running.
- Access Dagster UI after deploy:  
  `kubectl -n alpes-water-monitor port-forward deploy/dagster-webserver 3000:3000`
- Access MinIO console (optional):  
  `kubectl -n alpes-water-monitor port-forward deploy/minio 9000:9000 9001:9001`

## Configuration & secrets
Set env vars (see `.env.example`):
- `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`
- `ALPES_MINIO_ENDPOINT` (e.g., `http://minio:9000`)
- `ALPES_MINIO_BUCKET` (default `alpes-water-monitor`)
- `ALPES_MINIO_ACCESS_KEY`, `ALPES_MINIO_SECRET_KEY`

Kubernetes secret example:
```bash
kubectl -n alpes-water-monitor create secret generic cdse-credentials \
  --from-literal=client_id=YOUR_ID \
  --from-literal=client_secret=YOUR_SECRET
```

## Local development
```bash
python -m venv .env
source .env/bin/activate   # or .env\Scripts\activate on Windows
pip install -r requirements.txt
# set env vars (CDSE, MinIO)
PYTHONPATH=./src pytest
```

## Tests
- Run all: `PYTHONPATH=./src pytest`
- Covers Dagster defs import and NDWI domain logic (rasterization, metrics, deltas).

## CDSE credential setup (quick)
1. Create account on https://dataspace.copernicus.eu/.
2. Register an app to get `client_id` and `client_secret`.
3. Create/update the `cdse-credentials` secret in the cluster (see above).
4. Ensure MinIO env vars are set in deployments.

