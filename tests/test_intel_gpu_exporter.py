"""Tests for scripts/intel_gpu_exporter.py: a fake sysfs tree and a fake intel_gpu_top that prints JSON samples."""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING

import intel_gpu_exporter as ex
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

A310 = "0000:43:00.0"
# One sample as intel_gpu_top 2.0 prints it for a discrete card: no power (that's hwmon's), no clients.
SAMPLE = {
    "period": {"duration": 1000.0, "unit": "ms"},
    "frequency": {"requested": 2000.0, "actual": 1950.0, "unit": "MHz"},
    "interrupts": {"count": 12.0, "unit": "irq/s"},
    "rc6": {"value": 25.0, "unit": "%"},
    "engines": {
        "Render/3D": {"busy": 10.0, "sema": 0.0, "wait": 0.0, "unit": "%"},
        "Video": {"busy": 50.0, "sema": 0.0, "wait": 0.0, "unit": "%"},
        "VideoEnhance": {"busy": 0.0, "sema": 0.0, "wait": 0.0, "unit": "%"},
    },
}


def pci_device(sysfs: Path, slot: str, vendor: str, pci_class: str, driver: str | None) -> None:
    dev = sysfs / "bus/pci/devices" / slot
    dev.mkdir(parents=True)
    (dev / "vendor").write_text(vendor + "\n")
    (dev / "class").write_text(pci_class + "\n")
    if driver:
        target = sysfs / "bus/pci/drivers" / driver
        target.mkdir(parents=True, exist_ok=True)
        (dev / "driver").symlink_to(target)


@pytest.fixture
def sysfs(tmp_path: Path) -> Path:
    root = tmp_path / "sys"
    pci_device(root, A310, "0x8086", "0x030000", "i915")
    pci_device(root, "0000:0b:00.0", "0x102b", "0x030000", "mgag200")  # the server's own VGA chip
    pci_device(root, "0000:00:1f.3", "0x8086", "0x040300", "snd_hda_intel")  # Intel, but not a GPU
    pci_device(root, "0000:00:00.0", "0x8086", "0x060000", None)
    return root


def fake_top(tmp_path: Path, samples: list[dict], *, then: str = "sleep", stderr: str = "") -> list[str]:
    """A stand-in for intel_gpu_top: prints the samples like `-J` does, then sleeps or exits 1."""
    script = tmp_path / "fake_intel_gpu_top.py"
    body = "[\n" + ",\n".join(json.dumps(s, indent=1) for s in samples)
    script.write_text(
        "import sys, time\n"
        f"sys.stdout.write({body!r})\n"
        "sys.stdout.flush()\n"
        f"sys.stderr.write({stderr!r})\n" + ("time.sleep(60)\n" if then == "sleep" else "sys.exit(1)\n")
    )
    return [sys.executable, str(script)]


def wait_for(condition: object, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not condition():  # type: ignore[operator]
        if time.monotonic() > deadline:
            pytest.fail("timed out")
        time.sleep(0.02)


def metrics(text: str) -> dict[str, float]:
    return {
        line.rsplit(" ", 1)[0]: float(line.rsplit(" ", 1)[1])
        for line in text.splitlines()
        if line and not line.startswith("#")
    }


def test_find_gpus_lists_intel_display_controllers_with_their_driver(sysfs: Path) -> None:
    pci_device(sysfs, "0000:44:00.0", "0x8086", "0x038000", "vfio-pci")
    pci_device(sysfs, "0000:45:00.0", "0x8086", "0x030000", None)
    assert ex.find_gpus(sysfs) == {A310: "i915", "0000:44:00.0": "vfio-pci", "0000:45:00.0": ""}


def test_a_device_that_vanishes_while_being_read_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "bus/pci/devices/0000:01:00.0").mkdir(parents=True)  # no vendor file
    assert ex.find_gpus(tmp_path) == {}


def test_json_stream_returns_objects_as_they_complete() -> None:
    stream = ex.JsonStream()
    text = "[\n" + json.dumps(SAMPLE, indent=1) + ",\n" + json.dumps(SAMPLE, indent=1)
    cut = len(text) - 10
    assert stream.feed(text[:cut]) == [SAMPLE]
    assert stream.feed(text[cut:] + "\n]\n") == [SAMPLE]
    assert stream.feed('{"not": "a sample"}') == []
    assert stream.buffer == ""


def test_json_stream_drops_output_that_never_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ex, "MAX_BUFFER", 10)
    stream = ex.JsonStream()
    assert stream.feed("{garbage that is long") == []
    assert stream.buffer == ""


def test_samples_add_up_to_busy_and_idle_seconds() -> None:
    sample = ex.Sample()
    sample.add(SAMPLE, now=1)
    sample.add({**SAMPLE, "period": {"duration": 3000.0}, "power": {"GPU": 2.5, "Package": 9.0}}, now=2)
    assert sample.busy_seconds == pytest.approx({"Render/3D": 0.4, "Video": 2.0, "VideoEnhance": 0.0})
    assert sample.rc6_seconds == pytest.approx(1.0)
    assert sample.sampled_seconds == pytest.approx(4.0)
    assert sample.frequency_mhz == {"actual": 1950.0, "requested": 2000.0}
    assert sample.power_watts == {"gpu": 2.5, "package": 9.0}
    assert sample.updated == 2


def test_exporter_reports_a_running_gpu(sysfs: Path, tmp_path: Path) -> None:
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, [SAMPLE, SAMPLE]), period_ms=1000, retry=30)
    exporter.rescan()
    sampler = exporter.samplers[A310]
    assert sampler.command[-5:] == ["-J", "-s", "1000", "-d", f"pci:slot={A310}"]
    wait_for(lambda: sampler.sample.sampled_seconds == 2)
    got = metrics(exporter.render())
    assert got == {
        f'intel_gpu_info{{pci_slot="{A310}",driver="i915"}}': 1,
        f'intel_gpu_up{{pci_slot="{A310}"}}': 1,
        f'intel_gpu_top_failures_total{{pci_slot="{A310}"}}': 0,
        f'intel_gpu_engine_busy_seconds_total{{pci_slot="{A310}",engine="Render/3D"}}': pytest.approx(0.2),
        f'intel_gpu_engine_busy_seconds_total{{pci_slot="{A310}",engine="Video"}}': 1.0,
        f'intel_gpu_engine_busy_seconds_total{{pci_slot="{A310}",engine="VideoEnhance"}}': 0.0,
        f'intel_gpu_rc6_seconds_total{{pci_slot="{A310}"}}': 0.5,
        f'intel_gpu_sampled_seconds_total{{pci_slot="{A310}"}}': 2.0,
        f'intel_gpu_frequency_hertz{{pci_slot="{A310}",type="actual"}}': 1.95e9,
        f'intel_gpu_frequency_hertz{{pci_slot="{A310}",type="requested"}}': 2e9,
    }
    # A sample that's too old: intel_gpu_top hangs. The counters stay, the gauges go.
    later = metrics(exporter.render(now=time.monotonic() + 60))
    assert later[f'intel_gpu_up{{pci_slot="{A310}"}}'] == 0
    assert f'intel_gpu_rc6_seconds_total{{pci_slot="{A310}"}}' in later
    assert not [k for k in later if k.startswith("intel_gpu_frequency_hertz")]
    sampler.stop()
    assert sampler.process is not None
    assert sampler.process.poll() is not None


def test_mgag200_is_listed_but_only_i915_gpus_are_sampled(sysfs: Path, tmp_path: Path) -> None:
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, []), period_ms=1000, retry=30)
    exporter.rescan()
    assert set(exporter.samplers) == {A310}
    exporter.samplers[A310].stop()


def test_gpu_passed_through_to_a_vm_is_listed_and_not_sampled(sysfs: Path, tmp_path: Path) -> None:
    """The vfio case: no intel_gpu_top, no intel_gpu_up, and the exporter keeps answering."""
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, [SAMPLE]), period_ms=1000, retry=30)
    exporter.rescan()
    sampler = exporter.samplers[A310]
    wait_for(lambda: sampler.sample.updated > 0)
    driver = sysfs / f"bus/pci/devices/{A310}/driver"
    driver.unlink()
    (sysfs / "bus/pci/drivers/vfio-pci").mkdir()
    driver.symlink_to(sysfs / "bus/pci/drivers/vfio-pci")
    exporter.rescan()
    assert exporter.samplers == {}
    assert sampler.stopping.is_set()
    got = metrics(exporter.render())
    assert got[f'intel_gpu_info{{pci_slot="{A310}",driver="vfio-pci"}}'] == 1
    assert not [k for k in got if not k.startswith("intel_gpu_info")]
    # The card comes back to the host's driver: sampled again.
    driver.unlink()
    driver.symlink_to(sysfs / "bus/pci/drivers/i915")
    exporter.rescan()
    assert set(exporter.samplers) == {A310}
    exporter.samplers[A310].stop()


def test_intel_gpu_top_that_keeps_failing_counts_failures_and_reports_down(
    sysfs: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command = fake_top(tmp_path, [], then="exit", stderr="Failed to initialize PMU! (Permission denied)\n")
    exporter = ex.Exporter(sysfs, command, period_ms=1000, retry=0.05)
    exporter.rescan()
    sampler = exporter.samplers[A310]
    wait_for(lambda: sampler.failures >= 2)
    sampler.stop()
    got = metrics(exporter.render())
    assert got[f'intel_gpu_up{{pci_slot="{A310}"}}'] == 0
    assert got[f'intel_gpu_top_failures_total{{pci_slot="{A310}"}}'] >= 2
    assert "Failed to initialize PMU" in caplog.text


def test_missing_intel_gpu_top_is_a_failure_not_a_crash(sysfs: Path, tmp_path: Path) -> None:
    exporter = ex.Exporter(sysfs, [str(tmp_path / "missing")], period_ms=1000, retry=0.05)
    exporter.rescan()
    sampler = exporter.samplers[A310]
    wait_for(lambda: sampler.failures >= 1)
    sampler.stop()


def test_unexpected_sample_is_skipped(sysfs: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, [{"period": {}}, SAMPLE]), period_ms=1000, retry=30)
    exporter.rescan()
    sampler = exporter.samplers[A310]
    wait_for(lambda: sampler.sample.updated > 0)
    sampler.stop()
    assert "unexpected intel_gpu_top sample" in caplog.text


def test_watch_rescans_until_stopped(sysfs: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, []), period_ms=1000, retry=30)
    calls = []
    exporter.rescan = lambda: calls.append(1) or (_ for _ in ()).throw(OSError("sysfs"))  # type: ignore[method-assign]
    stop = threading.Event()
    thread = threading.Thread(target=exporter.watch, args=(0.01, stop))
    thread.start()
    wait_for(lambda: len(calls) >= 2)
    stop.set()
    thread.join()
    assert "looking for GPUs failed" in caplog.text


def test_label_values_are_escaped() -> None:
    assert ex.labels(engine='a"b\\c\n') == '{engine="a\\"b\\\\c\\n"}'


# The web side: basic auth with a bcrypt hash. bcrypt itself is faked; the exporter only calls checkpw.
HASH = "$2b$12$" + "x" * 53


@pytest.fixture
def fake_bcrypt(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    checked: list[bytes] = []

    def checkpw(password: bytes, hashed: bytes) -> bool:
        checked.append(password)
        return password == b"right" and hashed == HASH.encode()

    monkeypatch.setitem(sys.modules, "bcrypt", types.SimpleNamespace(checkpw=checkpw))
    return checked


@pytest.fixture
def server(sysfs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    exporter = ex.Exporter(sysfs, fake_top(tmp_path, []), period_ms=1000, retry=30)
    exporter.gpus = ex.find_gpus(sysfs)
    monkeypatch.setattr(ex.Handler, "exporter", exporter, raising=False)
    monkeypatch.setattr(ex.Handler, "password_hash", HASH)
    monkeypatch.setattr(ex.Handler, "accepted", set())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ex.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str, auth: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url)  # noqa: S310 # a local test server
    if auth is not None:
        request.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        with error:
            return error.code, ""


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_metrics_need_the_password(server: str, fake_bcrypt: list[bytes]) -> None:
    assert get(server + "/metrics")[0] == 401
    assert get(server + "/metrics", basic("argus", "wrong"))[0] == 401
    assert get(server + "/metrics", basic("someone", "right"))[0] == 401
    assert get(server + "/metrics", "Bearer right")[0] == 401
    assert get(server + "/metrics", "Basic !!!")[0] == 401
    status, body = get(server + "/metrics", basic("argus", "right"))
    assert status == 200
    assert f'intel_gpu_info{{pci_slot="{A310}",driver="i915"}} 1' in body
    # bcrypt ran once for the right password; the second scrape matches the remembered header.
    assert get(server + "/metrics", basic("argus", "right"))[0] == 200
    assert fake_bcrypt.count(b"right") == 1
    assert get(server + "/", basic("argus", "right"))[0] == 200
    assert get(server + "/other", basic("argus", "right"))[0] == 404


def test_metrics_are_open_without_a_hash(server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ex.Handler, "password_hash", None)
    assert get(server + "/metrics")[0] == 200


def test_password_hash_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv(ex.HASH_ENV, raising=False)
    assert ex.read_password_hash(None) is None
    monkeypatch.setenv(ex.HASH_ENV, HASH)
    assert ex.read_password_hash(None) == HASH
    (tmp_path / "password_hash").write_text(HASH.replace("x", "y") + "\n")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    assert ex.read_password_hash(None) == HASH.replace("x", "y")
    (tmp_path / "file").write_text("not a hash")
    with pytest.raises(ValueError, match="not a bcrypt hash"):
        ex.read_password_hash(str(tmp_path / "file"))


def test_parse_address() -> None:
    assert ex.parse_address(":9836") == ("", 9836)
    assert ex.parse_address("192.0.2.1:9836") == ("192.0.2.1", 9836)
    assert ex.parse_address("[::1]:9836") == ("::1", 9836)


def test_main_refuses_a_bad_hash(tmp_path: Path) -> None:
    (tmp_path / "hash").write_text("plain password")
    assert ex.main(["--web.password-hash-file", str(tmp_path / "hash")]) == 2


def test_main_serves_until_interrupted(sysfs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    monkeypatch.delenv(ex.HASH_ENV, raising=False)
    served = []

    def serve_forever(self: ThreadingHTTPServer) -> None:
        served.append(self.server_address)
        raise KeyboardInterrupt

    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", serve_forever)
    monkeypatch.setattr(ex.signal, "signal", lambda *_: None)
    command = fake_top(tmp_path, [])
    assert ex.main(["--web.listen-address", "127.0.0.1:0", "--sysfs", str(sysfs), "--intel-gpu-top", command[1]]) == 0
    assert served
    assert served[0][0] == "127.0.0.1"
