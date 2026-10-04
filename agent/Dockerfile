# Argus agent: Grafana Alloy with the Argus configuration baked in.
# See agent/README.md (or the main README) for how to run it.
FROM grafana/alloy:v1.20.1

COPY config.alloy /etc/alloy/config.alloy

ENV ARGUS_HOST="" \
    ARGUS_PROMETHEUS_URL="" \
    ARGUS_LOKI_URL=""

# The image's entrypoint is /bin/alloy; keep its default arguments.
CMD ["run", "/etc/alloy/config.alloy", "--storage.path=/var/lib/alloy/data"]
