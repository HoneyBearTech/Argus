# Argus agent: Grafana Alloy with the Argus configuration baked in.
# See "Adding a host" in the main README for how to run it.
FROM grafana/alloy:v1.21.2@sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18

# Apply Ubuntu's security updates to the base image's packages. Alloy's image can lag behind them
# (OpenSSL 3.0.13-0ubuntu3.16 at the time of writing), and the agent runs as root on every host.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY config.alloy /etc/alloy/config.alloy
# The same agent on a Kubernetes node (a DaemonSet runs it with `run /etc/alloy/kubernetes.alloy`).
COPY kubernetes.alloy /etc/alloy/kubernetes.alloy

ENV ARGUS_HOST="" \
    ARGUS_PROMETHEUS_URL="" \
    ARGUS_LOKI_URL=""

# The image's entrypoint is /bin/alloy; keep its default arguments.
CMD ["run", "/etc/alloy/config.alloy", "--storage.path=/var/lib/alloy/data"]
