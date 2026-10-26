# Argus Intel GPU exporter: scripts/intel_gpu_exporter.py with Debian's intel_gpu_top, for the Argus agent's
# intel-gpu profile (agent/compose.yml; docs/intel-gpu.md). Build context: repository root.
# amd64 only: Debian builds intel-gpu-tools for amd64 and i386.
FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad

# The base image's digest pins the release; the packages come with Debian's security updates at build time,
# like the agent's (agent/Dockerfile), rather than pinned versions that a point release removes.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends intel-gpu-tools python3-bcrypt \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/intel_gpu_exporter.py /usr/local/lib/argus/intel_gpu_exporter.py

# It runs as root with CAP_PERFMON as its only capability (agent/compose.yml): intel_gpu_top reads the GPU's
# counters through perf_event_open(), and Docker gives an added capability to root only.
EXPOSE 9836
ENTRYPOINT ["python3", "-I", "/usr/local/lib/argus/intel_gpu_exporter.py"]
