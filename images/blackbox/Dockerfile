# Argus blackbox_exporter: probe modules baked in.
# Build context: repository root.
FROM prom/blackbox-exporter:v0.28.0

COPY blackbox/blackbox.yml /etc/blackbox/blackbox.yml

CMD ["--config.file=/etc/blackbox/blackbox.yml"]
