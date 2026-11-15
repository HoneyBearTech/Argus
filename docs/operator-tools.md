# Setup, published-image upgrades and a status snapshot

These tools use the server's Python 3.12 or later and Docker Compose v2.24 or
later. Run them from the checkout that contains your installation's `.env`,
`targets/` and `secrets/`. They do not install system packages or start a
service
unless the command below explicitly says so.

## Guided setup

```sh
python3 scripts/setup.py
# Or accept the safe defaults without prompts:
python3 scripts/setup.py --defaults
```

The tool asks for the persistent data directory and optional Compose profiles.
It copies `.env.example` and `secrets.example/` into local configuration,
creates empty target lists corresponding to `targets.example/`, generates a
random Grafana admin password, and binds all three
published ports to loopback. Re-running it creates missing files and preserves
all existing files, including the password. It does not activate example targets
or configure real integration credentials: use `targets.example/` as a guide
when adding your network targets before starting. Files under `secrets/` are
readable by container users;
the enclosing host directory is private to the operator. Do not change its
permissions to make it accessible to other host users.

Read `secrets/grafana_admin_password` for the initial login. Review `.env`, the
files in `targets/` and `secrets/`, and the installation instructions in the
README, then validate and start:

```sh
docker compose config --quiet
docker compose up -d
```

Use a TLS proxy for remote agents and Grafana access; see
[push-security.md](push-security.md). The default loopback binds deliberately
require a local proxy before other machines can connect.

## Upgrade published images

Back up persistent data and local configuration as described in
[upgrading.md](upgrading.md). Obtain the checkout/configuration files matching
the target release first and review that release's migration notes. The command
updates the image selector, not the checkout or your persistent data.

```sh
python3 scripts/upgrade.py latest --dry-run
python3 scripts/upgrade.py 0.9.0
# Or resolve GitHub's latest stable published release:
python3 scripts/upgrade.py latest
```

Only stable published GitHub releases are accepted. Source-mode installations
and individual agent/GPU image overrides are refused. Remove shell image
version overrides before running. A dry run resolves the release and checks both
current and target Compose
configurations without pulling or starting images. It rejects Compose image
overrides that prevent the shared release selector from taking effect.

The command holds an installation lock, validates Compose, saves the previous
`.env` privately in `secrets/argus-upgrade.env.backup`, selects `ARGUS_VERSION`,
validates again, pulls all enabled services, and starts them with Compose's
health wait. It then checks Grafana and Prometheus, including the existing
Prometheus password. If validation, pulling, starting or application health
fails, it restores `.env`, starts the previous images and checks health again.
It exits nonzero on a failed upgrade, including when rollback succeeds.

Image rollback cannot reverse a database or storage migration. Keep your data
backup until the release is verified. After an interrupted command, inspect
`.env`, the backup and running images before retrying; restore the backup and
run `docker compose up -d --wait` to return to the previous selector. Remote
agent installations have independent Compose files and must be upgraded
separately. Dependency containers keep their explicitly pinned versions in the
checkout; updating the shared Argus selector does not update those pins.

## Read-only status page

```sh
python3 scripts/status_page.py --output /srv/www/argus-status.html
# If Prometheus requires its optional password:
python3 scripts/status_page.py --output /srv/www/argus-status.html \
  --password-file secrets/prometheus_password
```

The tool queries the expressions directly from the shipped Overview dashboard,
using all groups and a 24-hour range for range-dependent expressions. It writes
static HTML with a generation timestamp, escaped labels and values, and no
JavaScript, embedded credentials or requests from the reader's browser. A query
or write
failure leaves the previous page untouched through atomic replacement. Empty
successful results are shown
as "No data" rather than a healthy state. The output contains monitored system
names and labels: serve it only to your intended audience behind your existing
web server. Do not expose Prometheus itself to serve the page.

Run the command on a timer or cron schedule to refresh the snapshot. The page
shows the snapshot timestamp and does not automatically refresh. Use the
external heartbeat for detecting a stopped Argus server; a static page can
remain reachable after the monitoring stack stops.
