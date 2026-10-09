# Upgrading

Only the latest release gets fixes ([SUPPORT.md](../SUPPORT.md)), so upgrade when a new one comes out.
Every release's notes (and [CHANGELOG.md](../CHANGELOG.md)) list what changed and, under **Upgrading**,
anything you need to do first. Your data (metrics, logs, Grafana users and settings) lives in Docker
volumes and is kept across upgrades; dashboards and alert rules come from the image, so they're replaced
by the new version's.

## Server (published images)

1. Read the release notes, and do the "Upgrading" steps for every release between yours and the new one.
2. Optionally [verify the release](verifying-releases.md).
3. Set the new version in `.env` (`ARGUS_VERSION=0.5.1`), then:

   ```sh
   git pull                  # the compose file and examples can change between releases
   docker compose pull
   docker compose up -d
   ```

   Compare `.env.example`, `targets.example/` and `secrets.example/` with your own files for new
   settings.
4. Open Grafana and check the Homelab Overview. Grafana takes about 30 seconds to start; if it doesn't,
   `docker compose logs grafana` says why (usually a provisioning error).

With `ARGUS_VERSION=latest`, `docker compose pull && docker compose up -d` upgrades to whatever was
released last; pinning a version is recommended so that upgrades happen when you choose.

## Agents

On each host, set `ARGUS_AGENT_IMAGE` in the agent's `.env` to the new tag (for example
`ghcr.io/honeybeartech/argus-agent:0.5.1`), then `docker compose pull && docker compose up -d`. With
`docker run`, remove the container and run it again with the new tag. Agents and server don't need to be
upgraded at the same moment: an older agent keeps pushing to a newer server.

## Loki on a separate host

Set `ARGUS_VERSION` in that host's `.env`, then `docker compose pull && docker compose up -d`. Loki
reports "not ready" for about 15 seconds while it starts; agents retry their pushes meanwhile.

## Running from a checkout (source mode)

With `COMPOSE_FILE=docker-compose.yml:docker-compose.source.yml` in `.env`, you're running `main` (or
whatever you check out): `git pull && docker compose up -d --build`. To follow releases instead, check
out a tag (`git checkout v0.5.1`). To have the server pull and apply `main` by itself once CI has passed,
see [auto-deploy](auto-deploy.md).

## Rolling back

Set the previous version in `.env` (and in the agents' `.env`) and run `docker compose up -d`. Releases
before 1.0 don't migrate stored data, so going back is safe unless the release notes say otherwise.
Grafana's database (users, preferences) is not downgraded by older Grafana versions; if a downgrade
crosses a Grafana major version, keep a copy of the `grafana_data` volume from before the upgrade.
