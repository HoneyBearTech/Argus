# Argus agent: Grafana Alloy with the Argus configuration baked in.
# See "Adding a host" in the main README for how to run it.
FROM grafana/alloy:v1.21.1@sha256:4039c971193053a84e53dd9ed3e7d4561c069256b024631cd3498a353ed7ece8

# Apply Ubuntu's security updates to the base image's packages. Alloy's image can lag behind them
# (OpenSSL 3.0.13-0ubuntu3.16 at the time of writing), and the agent runs as root on every host.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY config.alloy /etc/alloy/config.alloy

ENV ARGUS_HOST="" \
    ARGUS_PROMETHEUS_URL="" \
    ARGUS_LOKI_URL=""

# The image's entrypoint is /bin/alloy; keep its default arguments.
CMD ["run", "/etc/alloy/config.alloy", "--storage.path=/var/lib/alloy/data"]
