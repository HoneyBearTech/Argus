# Argus blackbox_exporter: probe modules baked in.
# Build context: repository root.
FROM prom/blackbox-exporter:v0.29.1@sha256:ea1c7aa3ef3f307cd03e85f34abb604478ccb90b567fc690da0cd9776da76b13

COPY blackbox/blackbox.yml /etc/blackbox/blackbox.yml

# The upstream image runs as root. Argus' HTTP and DNS probes don't need it
# (ICMP probes would).
USER 65534:65534

CMD ["--config.file=/etc/blackbox/blackbox.yml"]
