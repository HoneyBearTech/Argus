# Contributing to Argus

Argus is a personal project with a single maintainer. Contributions are welcome, but there is no
service-level agreement, and review may take a while. Releases are tagged `vMAJOR.MINOR.PATCH`; only the
latest release and `main` are supported.

## Reporting bugs and suggesting changes

- Use [GitHub Issues](https://github.com/HoneyBearTech/Argus/issues) for bugs, questions and ideas for new
  dashboards, alerts or integrations. For anything bigger than a small fix, please open an issue first so we
  can agree on the approach before you spend time on it.
- **Do not report security vulnerabilities in a public issue.** Follow [SECURITY.md](SECURITY.md) and use
  GitHub's private vulnerability reporting instead.

## Development setup

Run the stack from your checkout so dashboard, alert and config edits apply without rebuilding images:

```sh
cp .env.example .env    # set GF_SECURITY_ADMIN_PASSWORD; use 127.0.0.1 binds for a local sandbox
echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.source.yml' >> .env
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp secrets.example/* secrets/
docker compose up -d --build
```

Grafana picks up dashboard JSON edits within 30 seconds. Restart Grafana after changing `provisioning/`
(alert rules, datasources) and Prometheus after changing `prometheus/prometheus.yml`. Grafana refuses to start
on an invalid provisioned alert rule, so always load alerting changes in a sandbox before opening a pull
request.

See "Adding or changing a dashboard" in the [README](README.md#adding-or-changing-a-dashboard) for dashboard
conventions: a stable hand-picked `uid`, `"id": null`, the `argus` tag, a description of the question it
answers, and datasources referenced by uid.

## Before you open a pull request

Run the checks CI runs and make sure they pass:

```sh
python3 scripts/check_dashboards.py    # dashboard conventions; no private IPs or internal names
docker run --rm -v "$PWD/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$PWD/targets.example:/etc/prometheus/targets:ro" -v "$PWD/secrets.example:/etc/prometheus/secrets:ro" \
  --entrypoint promtool prom/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml
GF_SECURITY_ADMIN_PASSWORD=x docker compose -f docker-compose.yml config --quiet
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) additionally validates the blackbox, Loki and
Alloy configs, builds every image, and checks both compose files. CodeQL and OpenSSF Scorecard also run on
the repository.

## Pull requests

- `main` is protected: changes land only through a pull request, and the required CI check must pass. Pull
  requests are squash-merged.
- Keep each pull request focused on one change, and describe what it does and why.
- When you add a dashboard, alert or scrape job, extend the checks if they don't cover it, add placeholders to
  `targets.example/` or `secrets.example/`, and update `README.md` and `.env.example` if you change
  configuration or user-visible behaviour.
- Follow the style of the surrounding files rather than introducing a new one.
- **This repository is public.** Never commit IP addresses, internal hostnames or domains, credentials,
  tokens or `.env` files. Real targets go in `targets/` and credentials in `secrets/`, both gitignored. Review
  exported dashboard JSON before committing: Grafana bakes current variable values and query text into it.
  Secret scanning and push protection are enabled on the repository.
- Upstream image bumps (Grafana, Prometheus, Loki, blackbox_exporter, Alloy) are pinned by digest; bump the
  matching version in `.github/workflows/ci.yml` too, and load the change in a sandbox, since CI's static
  checks don't start Grafana.

## License

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
