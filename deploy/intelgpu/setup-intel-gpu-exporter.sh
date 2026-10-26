#!/usr/bin/env bash
# Set up Argus' Intel GPU exporter (scripts/intel_gpu_exporter.py, which reads intel_gpu_top) as a systemd
# service on a Debian server whose own i915 driver has an Intel GPU (a Proxmox VE node sharing an Arc card with a
# container, for example), for the Intel GPU panels on Argus' Server Hardware dashboard. See docs/intel-gpu.md.
#
# Usage: copy it and the exporter to the server, then run it there as root with the bcrypt hash of the exporter's
# password on stdin (one line; the password itself stays on the Argus server). From the Argus checkout:
#   scp deploy/intelgpu/setup-intel-gpu-exporter.sh scripts/intel_gpu_exporter.py root@<server>:
#   htpasswd -niB -C 12 argus < secrets/intel_gpu_password | head -1 | cut -d: -f2- \
#     | ssh root@<server> ./setup-intel-gpu-exporter.sh <server-address>
#
# Result: the exporter running as a transient unprivileged user (systemd's DynamicUser) whose only capability is
# CAP_PERFMON, which intel_gpu_top needs to read the GPU's performance counters (the i915 PMU); the kernel's
# perf_event_paranoid stays as it is. No device files, no writable path, listening on <server-address>:9836 only,
# behind basic auth (user `argus`). The service waits for the network at boot and keeps retrying until its address
# exists. A GPU passed through to a VM (vfio-pci) is reported as such, not as a failure. Safe to run again: it
# rewrites the same files each time.
set -euo pipefail

LISTEN_IP=${1:?usage: $0 <listen-ip>  (bcrypt hash on stdin)}
PORT=9836
SERVICE=argus-intel-gpu-exporter
EXPORTER=$(dirname "$0")/intel_gpu_exporter.py
read -r HASH
# shellcheck disable=SC2016 # a literal bcrypt prefix ($2a$, $2b$ or $2y$), not an expansion
case $HASH in '$2'[aby]'$'*) ;; *) echo "stdin is not a bcrypt hash" >&2; exit 1 ;; esac
ip -4 -o addr show | grep -qw "$LISTEN_IP" || { echo "$LISTEN_IP is not an address of this host" >&2; exit 1; }
[ -f "$EXPORTER" ] || { echo "$EXPORTER not found: copy scripts/intel_gpu_exporter.py next to this script" >&2; exit 1; }

# 1. intel_gpu_top (intel-gpu-tools, no services of its own) and bcrypt for the password check. No Recommends.
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends intel-gpu-tools python3-bcrypt >/dev/null
echo "intel-gpu-tools $(dpkg-query -W -f='${Version}' intel-gpu-tools)"

# 2. The exporter (root-owned, read-only to the service) and the password hash, which systemd hands the service as
#    a credential, so the hash file itself stays readable by root only.
install -D -m 755 -o root -g root "$EXPORTER" /usr/local/lib/argus/intel_gpu_exporter.py
install -d -m 700 /etc/argus
umask 077
printf '%s\n' "$HASH" > /etc/argus/intel-gpu-exporter.hash
umask 022

# 3. The unit: the exporter's own, so the boot ordering and retries are in it rather than in a drop-in.
cat > /etc/systemd/system/$SERVICE.service <<EOF
# Argus: Intel GPU exporter (docs/intel-gpu.md). Written by deploy/intelgpu/setup-intel-gpu-exporter.sh.
[Unit]
Description=Argus Intel GPU exporter (intel_gpu_top)
Documentation=https://github.com/HoneyBearTech/Argus/blob/main/docs/intel-gpu.md
# It listens on the server's own address, which a bridge (Proxmox' vmbr0) may not have yet early in boot; start
# once the network is up, and retry every 5 s for as long as it takes rather than giving up after 5 fast failures.
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
ExecStart=/usr/bin/python3 -I /usr/local/lib/argus/intel_gpu_exporter.py --web.listen-address=${LISTEN_IP}:${PORT}
LoadCredential=password_hash:/etc/argus/intel-gpu-exporter.hash
Restart=on-failure
RestartSec=5s
# Unprivileged, with CAP_PERFMON only: intel_gpu_top opens the i915 PMU through perf_event_open().
DynamicUser=yes
AmbientCapabilities=CAP_PERFMON
CapabilityBoundingSet=CAP_PERFMON
NoNewPrivileges=yes
# Everything else it doesn't need: it reads sysfs and /proc, and writes nothing.
PrivateDevices=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectProc=invisible
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
SystemCallFilter=@system-service perf_event_open
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
chmod 644 /etc/systemd/system/$SERVICE.service
systemctl daemon-reload

# 4. Start, then check: active, listening on the one address only, refusing scrapes without the password, and
#    intel_gpu_top running (it exits at once if it can't open the PMU).
systemctl enable $SERVICE >/dev/null 2>&1
systemctl restart $SERVICE
sleep 4
systemctl is-active --quiet $SERVICE || { journalctl -u $SERVICE -n 20 --no-pager; exit 4; }
listening=$(ss -ltnH "( sport = :$PORT )" | awk '{print $4}' | sort -u | tr '\n' ' ')
[ "$listening" = "${LISTEN_IP}:${PORT} " ] || { echo "listening on '$listening', expected ${LISTEN_IP}:${PORT} only" >&2; exit 5; }
code=$(curl -s -o /dev/null -w '%{http_code}' "http://${LISTEN_IP}:${PORT}/metrics")
[ "$code" = 401 ] || { echo "a scrape without the password got HTTP $code, expected 401" >&2; exit 6; }
echo "service active, listening on ${LISTEN_IP}:${PORT}, 401 without the password"
journalctl -u $SERVICE --since "-10s" -o cat --no-pager | grep -E "Intel GPUs|intel_gpu_top" || true
if journalctl -u $SERVICE --since "-10s" -o cat --no-pager | grep -q "intel_gpu_top exited"; then
  echo "intel_gpu_top fails as the service's user; see the lines above (CAP_PERFMON not enough for this kernel?)" >&2
  exit 7
fi
