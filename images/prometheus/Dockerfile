# Argus Prometheus: scrape configuration baked in. Targets (targets/) and
# credentials (secrets/) are mounted at run time.
# Build context: repository root.
FROM prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06

COPY prometheus/prometheus.yml /etc/prometheus/prometheus.yml
