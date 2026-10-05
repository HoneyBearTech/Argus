# Contributing to Argus

Argus is a personal project with a single maintainer (see [GOVERNANCE.md](GOVERNANCE.md)). Contributions
are welcome, but there is no service-level agreement, and review may take a while. Releases are tagged
`vMAJOR.MINOR.PATCH`; only the latest release and `main` are supported ([SUPPORT.md](SUPPORT.md)).
Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and suggesting changes

- Use [GitHub Issues](https://github.com/HoneyBearTech/Argus/issues) for bugs, questions and ideas for new
  dashboards, alerts or integrations. For anything bigger than a small fix, please open an issue first so we
  can agree on the approach before you spend time on it. The [roadmap](docs/roadmap.md) says what's
  planned and what's out of scope.
- **Do not report security vulnerabilities in a public issue.** Follow [SECURITY.md](SECURITY.md) and use
  GitHub's private vulnerability reporting instead.

## Development setup

You need git, Docker with Compose v2.24 or later, and Python 3.12 or later for the checks and tests. Run
the stack from your checkout so dashboard, alert and config edits apply without rebuilding images:

```sh
git clone https://github.com/HoneyBearTech/Argus.git && cd Argus
cp .env.example .env    # set GF_SECURITY_ADMIN_PASSWORD; use 127.0.0.1 binds for a local sandbox
echo 'COMPOSE_FILE=docker-compose.yml:docker-compose.source.yml' >> .env
mkdir -p targets secrets && cp targets.example/*.json targets/ && cp secrets.example/* secrets/
docker compose up -d --build

# the check and test tools, pinned with hashes
python3 -m venv .venv && .venv/bin/pip install --require-hashes --no-deps -r requirements-dev.txt
```

Grafana picks up dashboard JSON edits within 30 seconds. Restart Grafana after changing `provisioning/`
(alert rules, datasources) and Prometheus after changing `prometheus/prometheus.yml`. Grafana refuses to start
on an invalid provisioned alert rule, so load alerting changes in a sandbox before opening a pull request
(CI also starts the Grafana image and fails if anything didn't load).

See "Adding or changing a dashboard" in the [README](README.md#adding-or-changing-a-dashboard) for dashboard
conventions: a stable hand-picked `uid`, `"id": null`, the `argus` tag, a description of the question it
answers, and datasources referenced by uid. How the pieces fit together is in
[docs/architecture.md](docs/architecture.md).

### Building the images

Argus has no compiled code of its own: each image is a pinned upstream image with Argus' configuration
copied in. Everything it needs comes from the Dockerfiles (base images pinned by digest) and the
repository itself; [docs/dependencies.md](docs/dependencies.md) lists them.

```sh
docker build -t argus-agent:dev agent/
for image in grafana prometheus blackbox loki; do
  docker build -t "argus-${image}:dev" -f "images/${image}/Dockerfile" .   # build context: repo root
done
```

A locally built image matches your machine's architecture. The release workflow builds amd64 and arm64
with `docker buildx` ([`.github/workflows/release.yml`](.github/workflows/release.yml)).

## When and how tests run

Every push and pull request runs one CI job, "Dashboards + config"
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)), which is the required check on `main`. It runs
the linters below, the unit tests with a coverage floor, the dashboard and public-repo checks, `promtool`
on the Prometheus config and the PromQL tests, config checks for blackbox, Loki and Alloy, builds every
image, starts the Grafana image to check that every dashboard, alert rule, datasource and the contact
point loads, and validates the compose files. CodeQL, a weekly image vulnerability scan and OpenSSF
Scorecard also run on the repository, and pull requests need a DCO sign-off (below).

## Before you open a pull request

Run what CI runs and make sure it passes:

```sh
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/yamllint --strict .
.venv/bin/coverage run -m pytest && .venv/bin/coverage report
python3 scripts/check_dashboards.py    # dashboard conventions; no private IPs or internal names

# PromQL tests: the shipped queries against tests/promql/
.venv/bin/python scripts/promql_tests.py --out /tmp/argus-promql
docker run --rm -v /tmp/argus-promql:/tests:ro --entrypoint sh prom/prometheus:v3.15.0 \
  -c 'promtool test rules /tests/*.yml'

docker run --rm -v "$PWD/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$PWD/targets.example:/etc/prometheus/targets:ro" -v "$PWD/secrets.example:/etc/prometheus/secrets:ro" \
  --entrypoint promtool prom/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml
GF_SECURITY_ADMIN_PASSWORD=x docker compose -f docker-compose.yml config --quiet
```

The workflow, Dockerfile and Alloy linters run in containers; the exact commands are in
[`ci.yml`](.github/workflows/ci.yml).

## Coding standards

- **Python** (`scripts/`, `tests/`): [PEP 8](https://peps.python.org/pep-0008/) and
  [PEP 257](https://peps.python.org/pep-0257/), enforced by [ruff](https://docs.astral.sh/ruff/) with every
  rule family enabled (including type annotations and the bandit security rules) and `ruff format`; the
  few rules left out, and why, are in [`pyproject.toml`](pyproject.toml).
- **YAML** (compose files, provisioning, Prometheus, workflows): [yamllint](https://yamllint.readthedocs.io/)
  with [`.yamllint.yml`](.yamllint.yml), warnings treated as errors.
- **GitHub Actions workflows**: [actionlint](https://github.com/rhysd/actionlint), which also runs
  [shellcheck](https://www.shellcheck.net/) on every `run:` script. Actions are pinned by commit SHA, jobs
  ask for the fewest permissions they need, and untrusted values reach scripts through `env:`, never
  `${{ }}` inside `run:`.
- **Dockerfiles**: [hadolint](https://github.com/hadolint/hadolint), failing on any finding down to style;
  base images pinned by version and digest.
- **Alloy** (`agent/config.alloy`): formatted exactly as `alloy fmt` prints it.
- **Dashboards**: JSON as Grafana exports it (2-space indent; `scripts/check_dashboards.py --fix`
  rewrites it), plus the conventions in the README.
- Exceptions are made per line (for example `# noqa: S603 - reason`) with the reason next to them, never
  by turning a rule off for the whole repository.

## Test policy

- **New functionality comes with automated tests.** A new or changed alert rule or dashboard query gets a
  PromQL test in [`tests/promql/`](tests/promql/) showing which series it returns (or alerts on) and which
  it must not; a change to a script in `scripts/` gets pytest tests in [`tests/`](tests/); a new
  security-relevant setting gets a test in [`tests/test_configs.py`](tests/test_configs.py).
- **Bug fixes come with a regression test** that fails before the fix, where the bug can be tested at all.
- Unit tests must keep statement and branch coverage of `scripts/` at or above the floor in
  `pyproject.toml` (90 %); CI fails below it.
- PromQL tests name the query instead of copying it (`rule: <uid>` or `dashboard: <uid>` + `panel:`), so
  they always test what ships; [`scripts/promql_tests.py`](scripts/promql_tests.py) explains the format.
- Anything that can't be tested automatically (for example how a panel looks) is checked in the sandbox
  and described in the pull request.

## Developer Certificate of Origin

Every commit must be signed off to certify the [Developer Certificate of Origin](https://developercertificate.org/):
that you wrote the change or otherwise have the right to submit it under the project's license. Add the
sign-off with `git commit -s`, which appends:

```
Signed-off-by: Your Name <you@example.com>
```

using your git `user.name` and `user.email`. The DCO check
([`.github/workflows/dco.yml`](.github/workflows/dco.yml)) fails a pull request with an unsigned commit;
fix it with `git rebase --signoff main` and force-push your branch.

## Pull requests

- `main` is protected: changes land only through a pull request, and the required CI check must pass. Pull
  requests are squash-merged.
- Keep each pull request focused on one change, and describe what it does and why.
- When you add a dashboard, alert or scrape job, add tests as described above, add placeholders to
  `targets.example/` or `secrets.example/`, and update `README.md`, `.env.example`, the docs and
  `CHANGELOG.md` (under "Unreleased") if you change configuration or user-visible behaviour.
- Follow the style of the surrounding files rather than introducing a new one.
- **This repository is public.** Never commit IP addresses, internal hostnames or domains, credentials,
  tokens or `.env` files. Real targets go in `targets/` and credentials in `secrets/`, both gitignored. Review
  exported dashboard JSON before committing: Grafana bakes current variable values and query text into it.
  Secret scanning and push protection are enabled on the repository.
- Upstream image bumps (Grafana, Prometheus, Loki, blackbox_exporter, Alloy) are pinned by digest; bump the
  matching version in `.github/workflows/ci.yml` too, and load the change in a sandbox.

## Releases

The maintainer adds a `## [x.y.z] - date` section to `CHANGELOG.md`, then pushes a signed tag
(`git tag -s vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`). The release workflow builds, signs and publishes
the images and creates the GitHub Release from that changelog section.

## License

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
