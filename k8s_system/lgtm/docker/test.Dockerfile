FROM redhat/ubi9

# renovate: datasource=github-releases depName=grafana packageName=grafana/grafana
ENV GRAFANA_VERSION=v11.2.2
# renovate: datasource=github-releases depName=prometheus packageName=prometheus/prometheus
ENV PROMETHEUS_VERSION=v2.54.1
# renovate: datasource=github-releases depName=tempo packageName=grafana/tempo
ENV TEMPO_VERSION=v2.6.0
# renovate: datasource=github-releases depName=loki packageName=grafana/loki
ENV LOKI_VERSION=v3.2.0
# renovate: datasource=github-releases depName=opentelemetry-collector packageName=open-telemetry/opentelemetry-collector-releases
ENV OPENTELEMETRY_COLLECTOR_VERSION=v0.111.0

# TARGETARCH is automatically detected and set by the Docker daemon during the build process.
ARG TARGETARCH=amd64
ENV TARGETARCH=${TARGETARCH}

RUN mkdir /otel-lgtm
WORKDIR /otel-lgtm

RUN yum install -y unzip jq procps dos2unix

RUN GRAFANA_VERSION_NO_V=$(echo ${GRAFANA_VERSION} | sed 's/^v//') && \
    ARCHIVE=grafana-${GRAFANA_VERSION_NO_V}.linux-${TARGETARCH}.tar.gz && \
    echo "Downloading ${ARCHIVE}" && \
    curl -fOL https://dl.grafana.com/oss/release/${ARCHIVE} && \
    echo "Download complete. File info:" && \
    ls -lh ${ARCHIVE} && \
    echo "Attempting to extract..." && \
    tar -zxvf ${ARCHIVE} && \
    echo "Extraction complete. Contents:" && \
    ls -lh && \
    mv grafana-${GRAFANA_VERSION_NO_V} grafana && \
    rm ${ARCHIVE}