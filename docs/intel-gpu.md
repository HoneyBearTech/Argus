# Intel GPU load (intel_gpu_top)

The **Server Hardware** and **GPUs** dashboards' Intel GPU panels show how busy an Intel GPU is: the share of time its
Render/3D, Video (Quick Sync decode and encode) and VideoEnhance engines are busy, its clock and how much of the
time it idles in RC6. Temperature, fan and power come from the driver's hardware sensors instead
([hwmon](hwmon.md)); this page is about load.

The numbers come from `intel_gpu_top` (Debian's `intel-gpu-tools`), which reads the i915 driver's performance
counters. Argus' own small exporter, [`scripts/intel_gpu_exporter.py`](../scripts/intel_gpu_exporter.py), runs
it and serves what it reads to Prometheus. It runs in one of two ways:

- **on a server**, as a systemd service, when the server's own i915 driver has the GPU, such as a Proxmox VE
  node that shares an Arc card with a container ([`deploy/intelgpu/`](../deploy/intelgpu/));
- **on a host or VM with the Argus agent**, as the agent's `intel-gpu` profile, when that machine's driver has
  the GPU, such as a VM the card is passed through to.

## How it works

```
server or VM ── i915 driver ── PMU counters ◀── intel_gpu_top -J (every second)
  └ intel_gpu_exporter :9836 (basic auth) ◀── scrape, job "intel_gpu" ── Prometheus (Argus server)
```

- The exporter finds the Intel GPUs on the PCI bus through sysfs and runs one `intel_gpu_top` per GPU that the
  i915 driver has. It needs no device file.
- Each sample's engine busy and RC6 percentages are added up, times the sample's length, into counters
  (`intel_gpu_engine_busy_seconds_total{engine}`, `intel_gpu_rc6_seconds_total`), so `rate()` over any window
  is the exact share of that window, however short the bursts between scrapes. The clock
  (`intel_gpu_frequency_hertz{type="actual"|"requested"}`) is the last sample.
- `intel_gpu_info{pci_slot, driver}` lists every Intel GPU with the driver that has it, and
  `intel_gpu_up{pci_slot}` is 1 while `intel_gpu_top` reports a GPU on i915 and 0 while it can't.
- It looks for GPUs again every 30 seconds, so a card that changes driver is picked up.
- Series carry the GPU's PCI address (`pci_slot`); Prometheus adds the `host` label from the target.

**Permissions.** `intel_gpu_top` reads the counters through `perf_event_open()`. For counters that cover the
whole system, as a GPU's do, the kernel requires `CAP_PERFMON` (or root), and a Debian, Ubuntu or Proxmox
kernel's `kernel.perf_event_paranoid` of 3 or 4 doesn't change that. The exporter gets exactly that one
capability; the system setting stays as it is. (Ubuntu kernels before the fix for
[LP #2131046](https://bugs.launchpad.net/ubuntu/+source/linux/+bug/2131046) asked for `CAP_SYS_ADMIN` at
paranoid level 4; on such a kernel `intel_gpu_top` fails with "Permission denied" and the **Intel GPU not
reporting** alert fires.)

**Which GPUs.** Those on the i915 driver: Arc (Alchemist) cards and integrated GPUs up to Meteor Lake. The xe
driver's GPUs are listed in `intel_gpu_info`, but `intel_gpu_top` 2.0 can't read them.

**Passthrough to a VM.** When the card is passed through to a VM (vfio-pci), the server's driver lets go of
it: the server's exporter lists it with `driver="vfio-pci"`, runs nothing for it and keeps answering, so
nothing alerts. If the VM runs the agent's `intel-gpu` profile, the VM reports the card from then on, under its
own name and its own PCI address for the card.

## Setting up a server

Requirements: Debian 13 (or Proxmox VE 9), the card on the i915 driver (`lspci -k` says `Kernel driver in use:
i915`), and `apache2-utils` (`htpasswd`) on the Argus server.

1. On the Argus server, create the exporter's password once (all servers and agents share it):

   ```sh
   openssl rand -base64 33 | tr -d '/+=\n' | head -c 32 > secrets/intel_gpu_password
   chmod 644 secrets/intel_gpu_password   # Prometheus' container reads it, like the other secrets
   ```

2. Copy [`deploy/intelgpu/setup-intel-gpu-exporter.sh`](../deploy/intelgpu/setup-intel-gpu-exporter.sh) and
   the exporter to the server and run the script as root with the password's bcrypt hash on stdin, so only the
   hash ever reaches the server:

   ```sh
   scp deploy/intelgpu/setup-intel-gpu-exporter.sh scripts/intel_gpu_exporter.py root@<server>:
   htpasswd -niB -C 12 argus < secrets/intel_gpu_password | head -1 | cut -d: -f2- \
     | ssh root@<server> ./setup-intel-gpu-exporter.sh <server-address>
   ```

   The script:
   - installs `intel-gpu-tools` and `python3-bcrypt` without their recommended packages;
   - installs the exporter as `/usr/local/lib/argus/intel_gpu_exporter.py` and the hash as
     `/etc/argus/intel-gpu-exporter.hash` (root only; systemd hands it to the service as a credential);
   - writes the unit `argus-intel-gpu-exporter.service`: a transient unprivileged user (`DynamicUser`) whose
     only capability is `CAP_PERFMON`, no device files, a read-only view of the system, listening on the
     given address, port 9836. It starts once the network is up and retries every 5 seconds without a limit,
     so a bridge that gets its address late in boot doesn't leave it down;
   - starts it and checks that it listens on that address only, refuses a scrape without the password, and
     that `intel_gpu_top` runs (it stops with an error if it can't).

   It can be run again at any time (after an update of the exporter, or to change the address).

3. On the Argus server, add the server to `targets/intel_gpu.json` with a `host` label (use the same name as in
   `targets/ipmi.json` and `targets/hwmon.json`):

   ```json
   [
     {"targets": ["<server-address>:9836"], "labels": {"host": "<server name>"}}
   ]
   ```

   Prometheus picks the file up without a restart. Check it from the Argus server:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' http://<server-address>:9836/metrics   # 401
   printf 'user = "argus:%s"\n' "$(cat secrets/intel_gpu_password)" \
     | curl -s -K - http://<server-address>:9836/metrics | grep '^intel_gpu_\(info\|up\)'
   ```

## Setting up a host or VM with the agent

The agent's `intel-gpu` profile runs the same exporter as a container, from the
`ghcr.io/honeybeartech/argus-intel-gpu-exporter` image (amd64 only; published from the first release after
0.7.1). In the host's agent `.env`:

```sh
COMPOSE_PROFILES=intel-gpu          # with the others, comma-separated
# The bcrypt hash of the server's secrets/intel_gpu_password, in single quotes: Compose would read its $ signs.
ARGUS_INTEL_GPU_PASSWORD_HASH='$2y$12$…'
```

(`htpasswd -niB -C 12 argus < secrets/intel_gpu_password | head -1 | cut -d: -f2-` on the Argus server prints
the hash.) Then `docker compose up -d`, and add `<host>:9836` with its `host` label to `targets/intel_gpu.json`.

The container runs as root with `PERFMON` as its only capability, `no-new-privileges` and a read-only
filesystem, and gets no `/dev/dri` ([security](security.md#the-intel-gpu-exporters-perfmon)). Without a hash it
serves metrics to anyone who can reach port 9836, and says so in its log.

**A machine whose GPU can change**, such as a VM that fails over between a server with an NVIDIA card and one
with an Intel card, switches the profile on only while it has the Intel GPU, and says which GPU it booted with
through `homelab_gpu_selected{vendor}` ([interfaces](interfaces.md#data-contracts)). While that isn't `intel`,
its stopped Intel GPU exporter doesn't raise **Monitoring target down**, just as its NVIDIA exporter doesn't
while it isn't `nvidia`.

## What alerts, and what doesn't

**Intel GPU not reporting** (warning, after 10 minutes): a GPU is on the i915 driver but `intel_gpu_top`
can't read it (`intel_gpu_up` 0). The exporter's log (`journalctl -u argus-intel-gpu-exporter`, or
`docker logs argus-intel-gpu-exporter`) has `intel_gpu_top`'s own message, usually about permissions.

An exporter that is down raises the general **Monitoring target down**. A card passed through to a VM raises
nothing: its driver is vfio-pci, and the Intel GPUs table shows it as "Not sampled". A busy GPU doesn't alert;
a hot one does (**GPU hot**, from [hwmon](hwmon.md)).

## Security notes

- The exporter answers on the network with basic auth but without TLS, so the password crosses the LAN in the
  clear on every scrape; it's checked against a bcrypt hash, and the server keeps only the hash.
- What it serves: the GPUs' PCI addresses and drivers, engine busy time, clocks and idle time. No process names
  (it doesn't read `intel_gpu_top`'s per-client section).
- `CAP_PERFMON` lets a process read performance counters system-wide, which is more than the GPU's; it can't
  change anything. The service has no other privilege, and the server's `perf_event_paranoid` isn't lowered.
