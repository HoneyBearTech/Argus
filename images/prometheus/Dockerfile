# Argus Prometheus: scrape configuration baked in. Targets (targets/) and
# credentials (secrets/) are mounted at run time.
# Build context: repository root.
FROM prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e

COPY prometheus/prometheus.yml /etc/prometheus/prometheus.yml
