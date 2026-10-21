# Server hardware (IPMI)

The **Server Hardware** dashboard and the BMC alerts read each server's baseboard management controller (BMC:
Dell iDRAC, Supermicro IPMI and the like): temperatures, fans, voltages, power supplies, batteries, the live
power draw and how full the BMC's event log is. They answer *is the server hardware healthy?* — for example a
failed CMOS battery, a dead fan or a lost power supply, which the operating system never sees. Add-in cards
the BMC can't see, such as a third-party GPU, are read from the server's own driver instead: see
[hwmon](hwmon.md).

## How it works

```
server ── /dev/ipmi0 ── BMC
  └ prometheus-ipmi-exporter :9290 (basic auth) ◀── scrape, job "ipmi" ── Prometheus (Argus server)
```

[prometheus-ipmi-exporter](https://github.com/prometheus-community/ipmi_exporter) runs on the server itself,
from Debian's `prometheus-ipmi-exporter` package, and reads the server's own BMC through the local IPMI device.
No BMC password is involved and the BMC needn't be reachable over the network. The exporter runs as the
unprivileged `prometheus` user; reading the BMC needs root, so it calls four read-only
[FreeIPMI](https://www.gnu.org/software/freeipmi/) tools through `sudo`, which allows exactly the command lines
the exporter uses and nothing else (no clearing the event log, no power control, no power limits). It listens
on the server's own address, port 9290, behind basic auth.

Collectors: `ipmi` (sensors), `dcmi` (live power draw), `bmc` (BMC firmware and BIOS version) and `sel` (event
log size and free space).

## Setting up a server

Requirements: Debian 13 (or Proxmox VE 9), the IPMI device `/dev/ipmi0` (the kernel's `ipmi_si` and
`ipmi_devintf` modules, loaded automatically on servers with a BMC), and `apache2-utils` (`htpasswd`) on the
Argus server.

1. On the Argus server, create the exporter's password once (all servers share it):

   ```sh
   openssl rand -base64 33 | tr -d '/+=\n' | head -c 32 > secrets/ipmi_password
   chmod 644 secrets/ipmi_password   # Prometheus' container reads it, like the other secrets
   ```

2. Copy [`deploy/ipmi/setup-ipmi-exporter.sh`](../deploy/ipmi/setup-ipmi-exporter.sh) to the server and run it as
   root with the password's bcrypt hash on stdin, so only the hash ever reaches the server:

   ```sh
   scp deploy/ipmi/setup-ipmi-exporter.sh root@<server>:
   htpasswd -niB -C 12 argus < secrets/ipmi_password | head -1 | cut -d: -f2- \
     | ssh root@<server> ./setup-ipmi-exporter.sh <server-address>
   ```

   The script:
   - installs `prometheus-ipmi-exporter` (with `freeipmi-tools`) and `sudo` without letting Debian start the
     service on its default configuration, which listens on every address without a password;
   - writes `/etc/prometheus/ipmi_argus.yml` (the collectors, each run through `sudo`),
     `/etc/prometheus/ipmi_web.yml` (basic auth, user `argus`, the bcrypt hash) and the service's arguments in
     `/etc/default/prometheus-ipmi-exporter` (keeping the package's original as `….dist`); Debian's own
     `ipmi_local.yml` and `ipmi_remote.yml` stay untouched;
   - writes `/etc/sudoers.d/prometheus-ipmi-exporter` and checks it: the four read commands are allowed, and
     clearing the event log, power control, power limits, another config file, extra arguments and a shell are
     refused (checked with `sudo -l`, so nothing is run);
   - starts the service.

   It can be run again at any time (after a reinstall, or to change the address).

3. On the Argus server, add the server to `targets/ipmi.json` with a `host` label (the name the dashboard and
   alerts show):

   ```json
   [
     {"targets": ["<server-address>:9290"], "labels": {"host": "<server name>"}}
   ]
   ```

   Prometheus picks the file up without a restart. Check it from the Argus server:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' http://<server-address>:9290/metrics   # 401
   printf 'user = "argus:%s"\n' "$(cat secrets/ipmi_password)" \
     | curl -s -K - http://<server-address>:9290/metrics | grep '^ipmi_up'           # four collectors, all 1
   ```

## What alerts, and what doesn't

Sensor states are 0 (nominal), 1 (warning), 2 (critical) or NaN (not available). **Hardware sensor critical**
fires on state 2 for 5 minutes, **Hardware sensor warning** on state 1 for 15 minutes. Two kinds of sensor sit
at 2 without anything being wrong, so the rules — and the dashboard's counts and table, which use the same
selector — leave them out:

- *Entity Presence* sensors, which read 2 for a part that isn't fitted: an empty slot, an unused power supply
  bay, or a dedicated BMC network port on a board whose BMC shares a server port.
- Supermicro's `Pattern1`…`PatternN` LED pattern sensors.

**BMC not answering** fires when a collector can't read the BMC for 10 minutes, and **BMC event log full** when
less than 1 KiB is left. A server whose exporter is down raises the general **Monitoring target down**.

## A full event log

Many BMCs stop recording once their event log (SEL) is full, so a fault that happens then leaves no trace.
The exporter is deliberately not allowed to clear it. Save it, then clear it, as root on the server:

```sh
ipmi-sel --output-event-state > "sel-$(date +%F).txt"
ipmi-sel --clear
```

(or from the BMC's web page).

## When Debian updates the exporter

The sudo rules match the exporter's command lines exactly, as observed with package version `1.10.0-2+b4`. If
an upgrade changes them, the exporter's collectors report `ipmi_up 0` (and **BMC not answering** fires) and the
setup script refuses to lock the rules, saying so. To adapt: temporarily allow the four binaries with any
arguments, let one scrape run, read the command lines with `journalctl _COMM=sudo -o cat | grep COMMAND=`, and
update the rules and `EXPECTED_VERSION` in the script.

## Security notes

- The exporter answers on the network with basic auth but without TLS, so the password crosses the LAN in the
  clear on every scrape. Add `tls_server_config` to `ipmi_web.yml` and a `tls_config` to the `ipmi` job if
  that matters in your network.
- The `prometheus` user can read sensor data and the BMC's firmware version, and nothing else through sudo. It
  can't change BMC settings, power, the event log or anything on the server.
- `bmc_url` (the BMC's own network address, on `ipmi_bmc_info`) is dropped when Prometheus scrapes.
