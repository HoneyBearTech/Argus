#!/usr/bin/env bash
# Set up prometheus-ipmi-exporter on a Debian server (a Proxmox VE node, for example) for Argus' Server
# Hardware dashboard and BMC alerts. See docs/ipmi.md.
#
# Usage: copy it to the server, then run it there as root with the bcrypt hash of the exporter's password on
# stdin (one line; the password itself stays on the Argus server). From the Argus checkout:
#   scp deploy/ipmi/setup-ipmi-exporter.sh root@<server>:
#   htpasswd -niB -C 12 argus < secrets/ipmi_password | head -1 | cut -d: -f2- \
#     | ssh root@<server> ./setup-ipmi-exporter.sh <server-address>
#
# Result: Debian's prometheus-ipmi-exporter running as the unprivileged `prometheus` user, reading the
# server's own BMC through /dev/ipmi0 with four read-only FreeIPMI tools that sudo allows with their exact
# arguments and nothing else, listening on <server-address>:9290 only, behind basic auth (user `argus`).
# Safe to run again: it rewrites the same files and checks the sudo rules each time.
set -euo pipefail

LISTEN_IP=${1:?usage: $0 <listen-ip>  (bcrypt hash on stdin)}
EXPECTED_VERSION=1.10.0-2+b4   # the command lines in the sudoers rules were observed with this build
read -r HASH
# shellcheck disable=SC2016 # a literal bcrypt prefix ($2a$, $2b$ or $2y$), not an expansion
case $HASH in '$2'[aby]'$'*) ;; *) echo "stdin is not a bcrypt hash" >&2; exit 1 ;; esac
ip -4 -o addr show | grep -qw "$LISTEN_IP" || { echo "$LISTEN_IP is not an address of this host" >&2; exit 1; }

# 1. Install without letting Debian start the service with its default (unauthenticated, remote) config.
if ! dpkg -s prometheus-ipmi-exporter >/dev/null 2>&1; then
  [ -e /usr/sbin/policy-rc.d ] && { echo "/usr/sbin/policy-rc.d already exists; refusing" >&2; exit 1; }
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; chmod 755 /usr/sbin/policy-rc.d
  trap 'rm -f /usr/sbin/policy-rc.d' EXIT
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q prometheus-ipmi-exporter sudo >/dev/null
  rm -f /usr/sbin/policy-rc.d; trap - EXIT
fi
dpkg -s sudo >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -q sudo >/dev/null
v=$(dpkg-query -W -f='${Version}' prometheus-ipmi-exporter)
echo "prometheus-ipmi-exporter $v, freeipmi-tools $(dpkg-query -W -f='${Version}' freeipmi-tools), sudo $(dpkg-query -W -f='${Version}' sudo)"
if [ "$v" != "$EXPECTED_VERSION" ]; then
  echo "Package version differs from $EXPECTED_VERSION: re-observe the sudo command lines before locking sudoers. Stopping." >&2
  exit 2
fi

# 2. Config files (Debian's own ipmi_local.yml / ipmi_remote.yml stay untouched).
umask 027
cat > /etc/prometheus/ipmi_web.yml <<EOF
# Argus: basic auth for the IPMI exporter (exporter-toolkit web config). The password itself stays on the Argus server.
basic_auth_users:
  argus: $HASH
EOF
cat > /etc/prometheus/ipmi_argus.yml <<'EOF'
# Argus: local (in-band) IPMI via /dev/ipmi0. Each collector runs one read-only FreeIPMI tool through sudo;
# /etc/sudoers.d/prometheus-ipmi-exporter allows exactly those command lines and nothing else.
modules:
  default:
    collectors:
      - ipmi
      - dcmi
      - bmc
      - sel
    collector_cmd:
      ipmi: /usr/bin/sudo
      dcmi: /usr/bin/sudo
      bmc: /usr/bin/sudo
      sel: /usr/bin/sudo
    custom_args:
      ipmi: ["/usr/sbin/ipmimonitoring"]
      dcmi: ["/usr/sbin/ipmi-dcmi"]
      bmc: ["/usr/sbin/bmc-info"]
      sel: ["/usr/sbin/ipmi-sel"]
EOF
chown root:prometheus /etc/prometheus/ipmi_web.yml /etc/prometheus/ipmi_argus.yml
chmod 640 /etc/prometheus/ipmi_web.yml /etc/prometheus/ipmi_argus.yml
# Keep the package's original arguments once, for reference.
[ -e /etc/default/prometheus-ipmi-exporter.dist ] || cp -p /etc/default/prometheus-ipmi-exporter /etc/default/prometheus-ipmi-exporter.dist
sed -i "s|^ARGS=.*|ARGS=\"--config.file=/etc/prometheus/ipmi_argus.yml --web.listen-address=${LISTEN_IP}:9290 --web.config.file=/etc/prometheus/ipmi_web.yml\"|" \
  /etc/default/prometheus-ipmi-exporter

# 3. sudoers: exactly the four command lines the exporter runs (observed with $EXPECTED_VERSION).
T=$(mktemp)
cat > "$T" <<'EOF'
# Argus IPMI exporter: the four read-only FreeIPMI command lines it runs, matched exactly.
# The only variable part is the per-scrape FreeIPMI config file the exporter writes in its private /tmp.
Cmnd_Alias ARGUS_IPMI = \
    /usr/sbin/ipmimonitoring ^--quiet-cache --ignore-unrecognized-events --comma-separated-output --no-header-output --sdr-cache-recreate --output-event-bitmask --output-sensor-state --config-file /tmp/ipmi_exporter-[0-9a-f]{32}$, \
    /usr/sbin/ipmi-dcmi ^--get-system-power-statistics --config-file /tmp/ipmi_exporter-[0-9a-f]{32}$, \
    /usr/sbin/bmc-info ^--config-file /tmp/ipmi_exporter-[0-9a-f]{32}$, \
    /usr/sbin/ipmi-sel ^--info --config-file /tmp/ipmi_exporter-[0-9a-f]{32}$
prometheus ALL = (root) NOPASSWD: ARGUS_IPMI
EOF
visudo -cqf "$T"
install -m 0440 -o root -g root "$T" /etc/sudoers.d/prometheus-ipmi-exporter
rm -f "$T"
visudo -cq

# 4. Check the rules allow only what they should (list mode: nothing is executed).
X=/tmp/ipmi_exporter-0123456789abcdef0123456789abcdef
chk() { # $1 = expect allowed|denied, rest = command line
  local want=$1; shift
  if runuser -u prometheus -- sudo -n -l "$@" >/dev/null 2>&1; then got=allowed; else got=denied; fi
  [ "$got" = "$want" ] || { echo "SUDOERS CHECK FAILED: '$*' is $got, expected $want" >&2; exit 3; }
}
chk allowed /usr/sbin/ipmi-sel --info --config-file $X
chk allowed /usr/sbin/ipmi-dcmi --get-system-power-statistics --config-file $X
chk allowed /usr/sbin/bmc-info --config-file $X
chk allowed /usr/sbin/ipmimonitoring --quiet-cache --ignore-unrecognized-events --comma-separated-output --no-header-output --sdr-cache-recreate --output-event-bitmask --output-sensor-state --config-file $X
chk denied /usr/sbin/ipmi-sel --clear
chk denied /usr/sbin/ipmi-sel --info --config-file $X --clear
chk denied /usr/sbin/ipmi-dcmi --set-power-limit --power-limit-requested=100
chk denied /usr/sbin/ipmi-chassis --chassis-control=power-down
chk denied /usr/sbin/bmc-info --config-file /etc/evil
chk denied /bin/sh
echo "sudoers: 4 read commands allowed, 6 write/escalation probes denied"

# 5. Start.
systemctl enable prometheus-ipmi-exporter >/dev/null 2>&1
systemctl restart prometheus-ipmi-exporter
sleep 2
systemctl is-active --quiet prometheus-ipmi-exporter || { journalctl -u prometheus-ipmi-exporter -n 20 --no-pager; exit 4; }
echo "service active, listening on $(ss -ltnH '( sport = :9290 )' | awk '{print $4}' | tr '\n' ' ')"
