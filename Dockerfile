FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/alpes

COPY requirements.txt .

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
#COPY scripts ./scripts
COPY etc ./etc

ENV DAGSTER_HOME=/opt/dagster
RUN mkdir -p "$DAGSTER_HOME"
ENV PYTHONPATH=/opt/alpes/src

CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000"]
