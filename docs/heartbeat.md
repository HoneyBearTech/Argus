# Watch the watcher

An alert on the Argus server cannot report that its own power or network is
lost. Configure a **separate** dead-man-switch service, hosted elsewhere, to
expect a heartbeat every minute with at least a three-minute grace period.
Use its HTTPS success-ping URL (for example a Healthchecks-compatible endpoint).
That external service sends the missing-heartbeat notification through its own
notification channel, independently of Argus.

Save the URL in `secrets/heartbeat_url` using an editor, then set mode 0600.
The URL is a credential; it is never logged or passed as a command-line value.
The standard-library script checks Grafana `/api/health` and Prometheus
`/-/ready` on loopback, then sends the external ping only if both return 200.
It reads the optional `secrets/prometheus_password` for authenticated
Prometheus readiness. Redirects are refused for both checks and pings.

```sh
python3 scripts/heartbeat.py
mkdir -p ~/.config/systemd/user
cp deploy/systemd/argus-heartbeat.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now argus-heartbeat.timer
journalctl --user -u argus-heartbeat.service
```

The supplied user unit assumes the checkout is `~/Argus`. Adjust its paths for
another location. Keep the owning user's systemd manager running after logout
(enable user lingering through your host administrator if necessary). The timer
is opt-in; installing Argus alone sends no heartbeat traffic.

For custom ports, override the unit's `ExecStart` and pass one `--check` per
readiness URL; specifying any checks replaces the defaults. Include the two
core services and optionally Loki's loopback `/ready` endpoint. Each request
has a ten-second timeout. Adjust `TimeoutStartSec` if adding more checks.
The external heartbeat is a reachability signal, not a check of every exporter
or alert delivery channel. Test it by stopping the timer and confirming the
external service reports a missing heartbeat, then start the timer again.
