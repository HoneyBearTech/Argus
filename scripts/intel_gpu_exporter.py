#!/usr/bin/env python3
"""Prometheus exporter for Intel GPU load, read from intel_gpu_top (Debian's intel-gpu-tools).

It finds the Intel GPUs on the PCI bus in sysfs and runs one `intel_gpu_top -J` per GPU that the i915 driver
has, reading the JSON samples it prints every second. Engine busy time and RC6 (idle) residency are summed
into counters, so `rate()` over any window gives the exact share of time busy; frequency is the last sample.

intel_gpu_top reads the GPU's performance counters through the kernel's perf interface (the i915 PMU), which
takes CAP_PERFMON (or root); it needs no device file. A GPU that another driver has (vfio-pci: passed
through to a VM) is listed in intel_gpu_info and nothing else, and the exporter keeps answering, so it never
looks like a failure. GPUs are looked for again every 30 seconds, so one that comes back is picked up.

Basic auth (user `argus` by default) takes a bcrypt hash, from --web.password-hash-file, the systemd
credential `password_hash`, or the INTEL_GPU_EXPORTER_PASSWORD_HASH environment variable; checking it needs
python3-bcrypt. Otherwise only the standard library is used. See docs/intel-gpu.md.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

LOG = logging.getLogger("intel_gpu_exporter")
INTEL = "0x8086"
GPU_DRIVERS = {"i915"}  # the drivers intel_gpu_top 2.0 reads (its i915 PMU); xe GPUs are listed only
MAX_BUFFER = 1 << 20  # intel_gpu_top output that never parses is dropped rather than kept
HASH_ENV = "INTEL_GPU_EXPORTER_PASSWORD_HASH"
CREDENTIAL = "password_hash"


def find_gpus(sysfs: Path) -> dict[str, str]:
    """Intel display controllers (PCI class 0x03) on the PCI bus: {PCI address: kernel driver or ""}."""
    gpus = {}
    for dev in sorted((sysfs / "bus/pci/devices").glob("*")):
        try:
            vendor = (dev / "vendor").read_text().strip()
            pci_class = (dev / "class").read_text().strip()
        except OSError:
            continue
        if vendor == INTEL and pci_class.startswith("0x03"):
            driver = dev / "driver"
            gpus[dev.name] = driver.resolve().name if driver.exists() else ""
    return gpus


class Sample:
    """What one intel_gpu_top JSON object says, plus the counters summed from all of them."""

    def __init__(self) -> None:
        """Start with nothing sampled."""
        self.busy_seconds: dict[str, float] = {}
        self.rc6_seconds = 0.0
        self.sampled_seconds = 0.0
        self.frequency_mhz: dict[str, float] = {}
        self.power_watts: dict[str, float] = {}
        self.updated = 0.0  # time.monotonic() of the last sample; 0 = none yet

    def add(self, obj: dict[str, Any], now: float) -> None:
        """Add one sample: busy and RC6 percentages times the sample's duration; the latest clocks."""
        seconds = obj["period"]["duration"] / 1000
        self.sampled_seconds += seconds
        for engine, values in obj.get("engines", {}).items():
            self.busy_seconds[engine] = self.busy_seconds.get(engine, 0.0) + values["busy"] / 100 * seconds
        if "rc6" in obj:
            self.rc6_seconds += obj["rc6"]["value"] / 100 * seconds
        freq = obj.get("frequency", {})
        self.frequency_mhz = {kind: freq[kind] for kind in ("actual", "requested") if kind in freq}
        power = obj.get("power", {})
        self.power_watts = {name: power[key] for name, key in (("gpu", "GPU"), ("package", "Package")) if key in power}
        self.updated = now


class JsonStream:
    """Splits intel_gpu_top's JSON output ("[", then objects separated by commas) into objects as they arrive."""

    def __init__(self) -> None:
        """Start with an empty buffer."""
        self.buffer = ""
        self.decoder = json.JSONDecoder()

    def feed(self, text: str) -> list[dict[str, Any]]:
        """Add output; return the samples it completed."""
        self.buffer += text
        objects = []
        while True:
            self.buffer = self.buffer.lstrip("[,] \t\r\n")
            if not self.buffer:
                break
            try:
                obj, end = self.decoder.raw_decode(self.buffer)
            except json.JSONDecodeError:
                if len(self.buffer) > MAX_BUFFER:
                    LOG.warning("dropping %d bytes of intel_gpu_top output that don't parse", len(self.buffer))
                    self.buffer = ""
                break  # an incomplete object: wait for the rest
            self.buffer = self.buffer[end:]
            if isinstance(obj, dict) and "period" in obj:
                objects.append(obj)
        return objects


class Sampler:
    """Runs intel_gpu_top for one GPU, restarting it after `retry` seconds whenever it exits."""

    def __init__(self, slot: str, command: list[str], period_ms: int, retry: float) -> None:
        """Prepare to sample the GPU at PCI address `slot` every `period_ms`."""
        self.slot = slot
        self.command = [*command, "-J", "-s", str(period_ms), "-d", f"pci:slot={slot}"]
        self.period = period_ms / 1000
        self.retry = retry
        self.sample = Sample()
        self.failures = 0
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.process: subprocess.Popen[bytes] | None = None
        self.thread = threading.Thread(target=self.run, name=f"intel_gpu_top {slot}", daemon=True)

    def start(self) -> None:
        """Start sampling in a background thread."""
        self.thread.start()

    def stop(self) -> None:
        """Stop intel_gpu_top and the thread."""
        self.stopping.set()
        with self.lock:
            process = self.process
        if process and process.poll() is None:
            process.terminate()
        self.thread.join(timeout=5)

    def up(self, now: float) -> bool:
        """Whether the last sample is recent: intel_gpu_top is running and printing."""
        with self.lock:
            return self.sample.updated > 0 and now - self.sample.updated <= max(3 * self.period, self.period + 5)

    def run(self) -> None:
        """Run intel_gpu_top again and again, `retry` seconds apart, until stopped."""
        while not self.stopping.is_set():
            self.run_once()
            if not self.stopping.is_set():
                with self.lock:
                    self.failures += 1
                self.stopping.wait(self.retry)

    def run_once(self) -> None:
        """Run intel_gpu_top until it exits (or stop() ends it), adding up its samples."""
        try:
            process = subprocess.Popen(  # noqa: S603 # the command is the exporter's own argument
                self.command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except OSError as error:
            LOG.error("%s: can't run %s: %s", self.slot, self.command[0], error)  # noqa: TRY400 # no traceback
            return
        with self.lock:
            self.process = process
        if self.stopping.is_set():  # stop() came while it was starting
            process.terminate()
        with process:
            stream = JsonStream()
            stdout: Any = process.stdout  # a BufferedReader: read1() returns what's there
            while chunk := stdout.read1(65536):
                objects = stream.feed(chunk.decode(errors="replace"))
                with self.lock:
                    for obj in objects:
                        try:
                            self.sample.add(obj, time.monotonic())
                        except (KeyError, TypeError, ValueError) as error:
                            LOG.warning("%s: unexpected intel_gpu_top sample (%s)", self.slot, error)
            stderr = process.stderr.read().decode(errors="replace").strip() if process.stderr else ""
        if not self.stopping.is_set():
            LOG.error("%s: intel_gpu_top exited with %s: %s", self.slot, process.returncode, stderr.splitlines()[:3])


def escape(value: str) -> str:
    """Escape a label value for the Prometheus text format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels(**pairs: str) -> str:
    """Format a label set."""
    return "{" + ",".join(f'{key}="{escape(value)}"' for key, value in pairs.items()) + "}"


class Exporter:
    """Keeps one Sampler per GPU that the i915 driver has, and renders the metrics."""

    def __init__(self, sysfs: Path, command: list[str], period_ms: int, retry: float) -> None:
        """Prepare; rescan() finds the GPUs."""
        self.sysfs = sysfs
        self.command = command
        self.period_ms = period_ms
        self.retry = retry
        self.gpus: dict[str, str] = {}
        self.samplers: dict[str, Sampler] = {}
        self.lock = threading.Lock()

    def rescan(self) -> None:
        """Look for GPUs: start sampling the ones i915 has now, stop sampling the ones it no longer has."""
        gpus = find_gpus(self.sysfs)
        wanted = {slot for slot, driver in gpus.items() if driver in GPU_DRIVERS}
        with self.lock:
            if gpus != self.gpus:
                LOG.info("Intel GPUs: %s", ", ".join(f"{s} ({d or 'no driver'})" for s, d in gpus.items()) or "none")
            self.gpus = gpus
            gone = [self.samplers.pop(slot) for slot in set(self.samplers) - wanted]
            for slot in sorted(wanted - set(self.samplers)):
                self.samplers[slot] = Sampler(slot, self.command, self.period_ms, self.retry)
                self.samplers[slot].start()
        for sampler in gone:
            sampler.stop()

    def watch(self, interval: float, stop: threading.Event) -> None:
        """Rescan every `interval` seconds until `stop` is set."""
        while not stop.wait(interval):
            try:
                self.rescan()
            except OSError:
                LOG.exception("looking for GPUs failed")

    def render(self, now: float | None = None) -> str:
        """Render the metrics in the Prometheus text format."""
        now = time.monotonic() if now is None else now
        out: list[str] = []

        def family(name: str, kind: str, text: str, rows: list[tuple[str, float]]) -> None:
            out.append(f"# HELP {name} {text}\n# TYPE {name} {kind}\n")
            out.extend(f"{name}{row} {value!r}\n" for row, value in rows)

        with self.lock:
            gpus = dict(self.gpus)
            samplers = dict(self.samplers)
        family(
            "intel_gpu_info",
            "gauge",
            "An Intel GPU on the PCI bus and the kernel driver that has it (vfio-pci: passed through to a VM).",
            [(labels(pci_slot=slot, driver=driver), 1) for slot, driver in gpus.items()],
        )
        up, failures, busy, rc6, sampled, freq, power = [], [], [], [], [], [], []
        for slot, sampler in sorted(samplers.items()):
            is_up = sampler.up(now)
            up.append((labels(pci_slot=slot), int(is_up)))
            with sampler.lock:
                s = sampler.sample
                failures.append((labels(pci_slot=slot), sampler.failures))
                if not s.updated:
                    continue
                busy += [(labels(pci_slot=slot, engine=e), v) for e, v in sorted(s.busy_seconds.items())]
                rc6.append((labels(pci_slot=slot), s.rc6_seconds))
                sampled.append((labels(pci_slot=slot), s.sampled_seconds))
                if is_up:
                    freq += [(labels(pci_slot=slot, type=k), v * 1e6) for k, v in sorted(s.frequency_mhz.items())]
                    power += [(labels(pci_slot=slot, domain=d), v) for d, v in sorted(s.power_watts.items())]
        family("intel_gpu_up", "gauge", "1 while intel_gpu_top reports the GPU, 0 while it can't.", up)
        family("intel_gpu_top_failures_total", "counter", "Times intel_gpu_top exited or couldn't start.", failures)
        family(
            "intel_gpu_engine_busy_seconds_total", "counter", "Time an engine class was busy (rate() = share).", busy
        )
        family("intel_gpu_rc6_seconds_total", "counter", "Time the GPU spent in RC6, its idle power state.", rc6)
        family("intel_gpu_sampled_seconds_total", "counter", "Time covered by intel_gpu_top's samples.", sampled)
        family("intel_gpu_frequency_hertz", "gauge", "The GPU's actual and requested clock, last sample.", freq)
        family("intel_gpu_power_watts", "gauge", "Power as intel_gpu_top reads it (integrated GPUs only).", power)
        return "".join(out)


def check_password(password: str, password_hash: str) -> bool:
    """Check a password against its bcrypt hash."""
    import bcrypt  # noqa: PLC0415 # python3-bcrypt is needed only with a password

    return bcrypt.checkpw(password.encode(), password_hash.encode())


class Handler(BaseHTTPRequestHandler):
    """Serves /metrics, behind basic auth when a password hash is configured."""

    exporter: ClassVar[Exporter]
    username: ClassVar[str] = "argus"
    password_hash: ClassVar[str | None] = None
    # Authorization headers that passed, so bcrypt (slow on purpose) runs once per password, not per scrape.
    accepted: ClassVar[set[str]] = set()

    def authorized(self) -> bool:
        """Whether the request carries the right user and password (or no password is configured)."""
        if self.password_hash is None:
            return True
        header = self.headers.get("Authorization", "")
        if any(hmac.compare_digest(header, ok) for ok in list(self.accepted)):
            return True
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            user, _, password = base64.b64decode(encoded, validate=True).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return False
        if hmac.compare_digest(user, self.username) and check_password(password, self.password_hash):
            if len(self.accepted) < 16:  # noqa: PLR2004 # a bound on what a client can make it keep
                self.accepted.add(header)
            return True
        return False

    def do_GET(self) -> None:
        """Answer a GET: the metrics, a link to them, or 401/404."""
        if not self.authorized():
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="intel_gpu_exporter"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.split("?")[0] == "/metrics":
            body = self.exporter.render().encode()
            content_type = "text/plain; version=0.0.4; charset=utf-8"
        elif self.path == "/":
            body = b'<html><body><a href="/metrics">Metrics</a></body></html>\n'
            content_type = "text/html"
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ANN401 # http.server's signature
        """Don't log every scrape."""


def read_password_hash(path: str | None) -> str | None:
    """Read the bcrypt hash from the file given, the systemd credential, or the environment; None = no auth."""
    credentials = os.environ.get("CREDENTIALS_DIRECTORY")
    if path is None and credentials and (Path(credentials) / CREDENTIAL).exists():
        path = str(Path(credentials) / CREDENTIAL)
    value = Path(path).read_text() if path else os.environ.get(HASH_ENV, "")
    value = value.strip()
    if value and not value.startswith(("$2a$", "$2b$", "$2y$")):
        msg = "the password hash is not a bcrypt hash"
        raise ValueError(msg)
    return value or None


def parse_address(address: str) -> tuple[str, int]:
    """Split host:port (host may be empty or [IPv6])."""
    host, _, port = address.rpartition(":")
    return host.strip("[]"), int(port)


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments, start sampling and serve until stopped."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web.listen-address", dest="listen", default=":9836", help="address:port (default :9836)")
    parser.add_argument("--web.username", dest="username", default="argus", help="basic auth user (default argus)")
    parser.add_argument("--web.password-hash-file", dest="hash_file", help="file with the password's bcrypt hash")
    parser.add_argument("--intel-gpu-top", default="intel_gpu_top", help="the intel_gpu_top command")
    parser.add_argument("--period", type=int, default=1000, help="intel_gpu_top's sample period in ms (default 1000)")
    parser.add_argument("--rescan", type=float, default=30, help="seconds between looks for GPUs (default 30)")
    parser.add_argument("--sysfs", type=Path, default=Path("/sys"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)

    try:
        password_hash = read_password_hash(args.hash_file)
    except (OSError, ValueError) as error:
        LOG.error("%s", error)  # noqa: TRY400 # a configuration error, not a crash
        return 2
    if password_hash is None:
        LOG.warning("no password hash configured: /metrics is open to anyone who can reach it")
    exporter = Exporter(args.sysfs, [args.intel_gpu_top], args.period, retry=args.rescan)
    exporter.rescan()
    stop = threading.Event()
    threading.Thread(target=exporter.watch, args=(args.rescan, stop), name="rescan", daemon=True).start()

    Handler.exporter = exporter
    Handler.username = args.username
    Handler.password_hash = password_hash
    server = ThreadingHTTPServer(parse_address(args.listen), Handler)
    LOG.info("listening on %s", args.listen)
    # systemd and Docker stop it with SIGTERM: stop intel_gpu_top too, rather than leave it running.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop.set()
        for sampler in list(exporter.samplers.values()):
            sampler.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
