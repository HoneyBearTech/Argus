#!/usr/bin/env bash
# Set up prometheus-node-exporter with only its hwmon collector on a Debian server that has no Argus agent (a
# Proxmox VE node, for example), for the GPU panels on Argus' Server Hardware dashboard and the GPU hot alert.
# See docs/hwmon.md.
#
# Usage: copy it to the server, then run it there as root with the bcrypt hash of the exporter's password on
# stdin (one line; the password itself stays on the Argus server). From the Argus checkout:
#   scp deploy/hwmon/setup-node-exporter.sh root@<server>:
#   htpasswd -niB -C 12 argus < secrets/hwmon_password | head -1 | cut -d: -f2- \
#     | ssh root@<server> ./setup-node-exporter.sh <server-address>
#
# Result: Debian's prometheus-node-exporter running as the unprivileged `prometheus` user with the hwmon
# collector only (the kernel drivers' hardware sensors under /sys/class/hwmon, which any user may read), listening
# on <server-address>:9100 only, behind basic auth (user `argus`). No sudo, no textfile directory, no other
# collectors. The service waits for the network at boot and keeps retrying until its address exists. Safe to run
# again: it rewrites the same files each time.
set -euo pipefail

LISTEN_IP=${1:?usage: $0 <listen-ip>  (bcrypt hash on stdin)}
read -r HASH
# shellcheck disable=SC2016 # a literal bcrypt prefix ($2a$, $2b$ or $2y$), not an expansion
case $HASH in '$2'[aby]'$'*) ;; *) echo "stdin is not a bcrypt hash" >&2; exit 1 ;; esac
ip -4 -o addr show | grep -qw "$LISTEN_IP" || { echo "$LISTEN_IP is not an address of this host" >&2; exit 1; }

# 1. Install without letting Debian start the service with its default config (every default collector, every
#    address, no password), and without its Recommends: prometheus-node-exporter-collectors runs timers as root.
if ! dpkg -s prometheus-node-exporter >/dev/null 2>&1; then
  [ -e /usr/sbin/policy-rc.d ] && { echo "/usr/sbin/policy-rc.d already exists; refusing" >&2; exit 1; }
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod 755 /usr/sbin/policy-rc.d
  trap 'rm -f /usr/sbin/policy-rc.d' EXIT
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends prometheus-node-exporter >/dev/null
  rm -f /usr/sbin/policy-rc.d; trap - EXIT
fi
echo "prometheus-node-exporter $(dpkg-query -W -f='${Version}' prometheus-node-exporter)"
if dpkg -s prometheus-node-exporter-collectors >/dev/null 2>&1; then
  echo "note: prometheus-node-exporter-collectors is installed; its root timers aren't needed here" >&2
fi

# 2. Config: basic auth, and the service's arguments (the package's original kept once as ….dist).
umask 027
cat > /etc/prometheus/node_exporter_web.yml <<EOF
# Argus: basic auth for node_exporter (exporter-toolkit web config). The password itself stays on the Argus server.
basic_auth_users:
  argus: $HASH
EOF
chown root:prometheus /etc/prometheus/node_exporter_web.yml
chmod 640 /etc/prometheus/node_exporter_web.yml
DEFAULTS=/etc/default/prometheus-node-exporter
[ -e $DEFAULTS.dist ] || cp -p $DEFAULTS $DEFAULTS.dist
ARGS="--collector.disable-defaults --collector.hwmon --web.disable-exporter-metrics"
ARGS="$ARGS --web.listen-address=${LISTEN_IP}:9100 --web.config.file=/etc/prometheus/node_exporter_web.yml"
if grep -q '^ARGS=' $DEFAULTS; then
  sed -i "s|^ARGS=.*|ARGS=\"$ARGS\"|" $DEFAULTS
else
  echo "ARGS=\"$ARGS\"" >> $DEFAULTS
fi
grep -qxF "ARGS=\"$ARGS\"" $DEFAULTS || { echo "couldn't set ARGS in $DEFAULTS" >&2; exit 1; }

# Wait for the network, and keep retrying. The service listens on the server's own address, which a bridge (Proxmox'
# vmbr0) may not have yet when the unit starts early in boot: "bind: cannot assign requested address". Debian's
# unit has no network ordering and systemd's default start limit (5 starts in 10 s) gives up for good.
DROPIN=/etc/systemd/system/prometheus-node-exporter.service.d/10-argus-wait-for-network.conf
install -d -m 755 "${DROPIN%/*}"
cat > "$DROPIN" <<'EOF'
# Argus: start once the network is up (ifupdown2's networking.service runs before network-online.target), and
# retry every 5 s for as long as it takes rather than giving up after 5 fast failures.
[Unit]
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Restart=on-failure
RestartSec=5s
EOF
chmod 644 "$DROPIN"
systemctl daemon-reload

# 3. Start, then check: active, listening on the one address only, and refusing scrapes without the password.
systemctl enable prometheus-node-exporter >/dev/null 2>&1
systemctl restart prometheus-node-exporter
sleep 2
systemctl is-active --quiet prometheus-node-exporter || { journalctl -u prometheus-node-exporter -n 20 --no-pager; exit 4; }
listening=$(ss -ltnH '( sport = :9100 )' | awk '{print $4}' | sort -u | tr '\n' ' ')
[ "$listening" = "${LISTEN_IP}:9100 " ] || { echo "listening on '$listening', expected ${LISTEN_IP}:9100 only" >&2; exit 5; }
code=$(curl -s -o /dev/null -w '%{http_code}' "http://${LISTEN_IP}:9100/metrics")
[ "$code" = 401 ] || { echo "a scrape without the password got HTTP $code, expected 401" >&2; exit 6; }
echo "service active, listening on ${LISTEN_IP}:9100, 401 without the password"

# 4. What the hwmon collector will report: each chip's driver name and the device it belongs to. node_exporter
#    names a chip after that device's path (a PCI card's chip label ends in its address), not after hwmonN.
for d in /sys/class/hwmon/hwmon*; do
  dev=$(readlink -f "$d/device" 2>/dev/null || true)
  echo "hwmon: $(cat "$d/name" 2>/dev/null || echo '?') ${dev:+(${dev##*/})}"
done
