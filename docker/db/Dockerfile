ARG POSTGIS_IMAGE=postgis/postgis:18-3.6
FROM ${POSTGIS_IMAGE}

ARG PGVECTOR_VERSION=v0.8.1

# Install pgvector from source so the DB image has BOTH PostGIS and pgvector.
# This keeps the OSS profile self-contained and avoids relying on distro packaging drift.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      git \
      build-essential \
      postgresql-server-dev-18 \
      ca-certificates; \
    git clone --depth 1 --branch ${PGVECTOR_VERSION} https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    cd /tmp/pgvector; \
    make; \
    make install; \
    rm -rf /tmp/pgvector; \
    apt-get purge -y git build-essential postgresql-server-dev-18; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*
