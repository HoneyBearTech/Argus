# Argus blackbox_exporter: probe modules baked in.
# Build context: repository root.
FROM prom/blackbox-exporter:v0.28.0@sha256:e753ff9f3fc458d02cca5eddab5a77e1c175eee484a8925ac7d524f04366c2fc

COPY blackbox/blackbox.yml /etc/blackbox/blackbox.yml

CMD ["--config.file=/etc/blackbox/blackbox.yml"]
