# Steerhouse

[Steerhouse](https://github.com/HoneyBearTech/Steerhouse) is a web UI for running Ansible playbooks. It ships
three Grafana dashboards and four example alert rules; Argus carries them, connected to its own Prometheus and to
Steerhouse's database:

| Dashboard (folder `ci`) | Answers |
| --- | --- |
| Steerhouse: overview & runs | Is Steerhouse healthy right now, and how have its Ansible runs gone: which failed, and how long did they take? |
| Steerhouse: execution, queue & workers | Is Steerhouse keeping up: are runs waiting for a worker, are notifications going out, and is its API healthy? |
| Steerhouse: security & access | Is anyone trying to get into Steerhouse, and who changed users, access or keys? |

They read two sources:

```
Steerhouse host
  ├ backend :8002 /metrics (bearer token) ◀── scrape every 30 s, job "steerhouse" ── Prometheus ──┐
  └ PostgreSQL :5432 (TLS only), role grafana_ro ◀── SQL, datasource "steerhouse-db" ── Grafana ◀─┘
```

- **Metrics** (what's happening now: queue, workers, API, notifications, sign-in failures) from the backend's
  metrics port, which answers only requests that send Steerhouse's `METRICS_TOKEN`.
- **History** (runs, durations, failures, sign-ins, audit events) from Steerhouse's database, as the
  `grafana_ro` role, which can read only the `analytics` views Steerhouse keeps for this. Grafana verifies the
  database's TLS certificate (`sslmode=verify-full`) and opens at most 5 connections, below the role's limit
  of 10.

## On the Steerhouse host

Steerhouse's own [README](https://github.com/HoneyBearTech/Steerhouse#monitoring-with-prometheus-and-grafana)
describes each setting; for Argus:

1. **Metrics.** Set `METRICS_TOKEN` (a long random string, `openssl rand -hex 32`) and `METRICS_HOST=0.0.0.0`
   in Steerhouse's `.env`, and publish the backend's port 8002 on an address the Argus server can reach. Allow
   only the Argus server to that port with a host firewall: the token crosses the network in plain HTTP.
2. **The database role.** As the database's owner:

   ```sql
   CREATE ROLE grafana_ro LOGIN PASSWORD '<a long random password>' NOINHERIT CONNECTION LIMIT 10;
   ALTER ROLE grafana_ro SET default_transaction_read_only = on;
   ALTER ROLE grafana_ro SET statement_timeout = '30s';
   ```

   then `python -m app.cli analytics-grant grafana_ro` in the backend container, and
   `python -m app.cli analytics-check grafana_ro` after Steerhouse upgrades.
3. **TLS for PostgreSQL.** Give PostgreSQL a certificate (`ssl=on`, `ssl_cert_file`, `ssl_key_file`) signed by
   a CA you keep, naming the address Argus connects to (an IP address goes in the certificate's
   `subjectAltName` as `IP:`). Publish port 5432 to the Argus server only, and in `pg_hba.conf` let
   `grafana_ro` in from there with `hostssl … scram-sha-256` and reject `hostnossl`.

## On the Argus server

| Where | What |
| --- | --- |
| `targets/steerhouse.json` | `[{"targets": ["<steerhouse host>:8002"]}]` |
| `secrets/steerhouse_metrics_token` | Steerhouse's `METRICS_TOKEN` |
| `secrets/steerhouse_db_password` | `grafana_ro`'s password |
| `secrets/steerhouse_db_ca` | the CA certificate (PEM) that signed PostgreSQL's certificate |
| `.env` | `STEERHOUSE_DB_ADDRESS=<steerhouse host>:5432`, the address the certificate names |

The three files must be readable by the containers (mode 644), without a trailing newline in the token and
password (`printf '%s' "$token" > secrets/steerhouse_metrics_token`). Then `docker compose up -d` (Grafana reads
its secrets at start). Prometheus picks up the target within a minute; the **Steerhouse: overview & runs**
dashboard's *Database* tile and its run history show whether both connections work.

Grafana needs `secrets/steerhouse_db_password` and `secrets/steerhouse_db_ca` even where Steerhouse isn't
watched: compose won't start Grafana without them, so keep the templates from `secrets.example/`. Without
`STEERHOUSE_DB_ADDRESS` the datasource has no address, and only the Steerhouse dashboards' history panels show
errors.

## Alerts

The `Steerhouse` alert group holds Steerhouse's four example rules, for trends only: Steerhouse's own
notifications already report single events (a failed run, a worker offline, a stuck queue, a login attack, an
admin change).

| Rule | Fires when |
| --- | --- |
| Steerhouse runs failing more than usual | more than 30 % of the runs that ended in the last hour failed or timed out, for 15 minutes |
| Steerhouse failed sign-ins spiking | more than 30 failed sign-ins in 15 minutes, across all user names and addresses |
| Steerhouse notifications not going out | a notification has waited more than 15 minutes to be sent, for 5 minutes |
| Steerhouse can't reach its database | the API's own reads of its database have failed for 5 minutes |

Steerhouse's example also fires when its metrics are missing altogether. In Argus that is **Monitoring target
down** (job `steerhouse`), which covers the API being down, a wrong token and an unreachable port; the
Steerhouse rule stays quiet where Steerhouse isn't scraped at all.

## When Steerhouse changes its dashboards

The dashboards are Steerhouse's own, ported by [`scripts/port_steerhouse.py`](../scripts/port_steerhouse.py):
it pins the datasource uids (`prometheus`, `steerhouse-db`) in place of Steerhouse's datasource variables,
gives them Argus' uids, tag and descriptions, adds a 30 s minimum interval to the Prometheus panels (the job's
scrape interval) and records the Steerhouse version in each description. Change them in Steerhouse, then port
again from a checkout of the release:

```sh
python3 scripts/port_steerhouse.py --steerhouse ../Steerhouse --version v0.10.1
python3 scripts/port_steerhouse.py --steerhouse ../Steerhouse --version v0.10.1 --check   # are they current?
```

Without `--version`, the version is `git describe` of the checkout. Then update
[`tests/promql/steerhouse.yml`](../tests/promql/steerhouse.yml) for any changed Prometheus query, and check every
query against a running Steerhouse in the sandbox.
