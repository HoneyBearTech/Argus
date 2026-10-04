# Argus Loki: single-process, local disk, 30-day retention.
# Build context: repository root.
FROM grafana/loki:3.7.8

COPY logs/loki.yaml /etc/loki/loki.yaml

CMD ["-config.file=/etc/loki/loki.yaml"]
