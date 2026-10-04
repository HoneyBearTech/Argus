# Argus Prometheus: scrape configuration baked in. Targets (targets/) and
# credentials (secrets/) are mounted at run time.
# Build context: repository root.
FROM prom/prometheus:v3.14.0

COPY prometheus/prometheus.yml /etc/prometheus/prometheus.yml
