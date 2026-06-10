FROM python:3.12.8-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    graphrag==2.2.0 \
    pandas==2.2.3 \
    pyarrow==18.1.0 \
    neo4j==5.27.0

COPY settings.yml .
COPY scripts/ scripts/

RUN chmod +x scripts/ingest.sh

ENTRYPOINT ["/bin/bash", "scripts/ingest.sh"]
