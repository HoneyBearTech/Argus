# Argus blackbox_exporter: probe modules baked in.
# Build context: repository root.
FROM prom/blackbox-exporter:v0.29.0@sha256:9613f2884689b6fad9f1939f6a3b0388c93a022cfaededb19545b329b5c83dea

COPY blackbox/blackbox.yml /etc/blackbox/blackbox.yml

# The upstream image runs as root. Argus' HTTP and DNS probes don't need it
# (ICMP probes would).
USER 65534:65534

CMD ["--config.file=/etc/blackbox/blackbox.yml"]
