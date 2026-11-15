# TLS push endpoints and an external heartbeat

## Authenticated agent traffic

Use [`docker-compose.tls.yml`](../docker-compose.tls.yml) with the server's
normal Compose file to terminate TLS and authenticate **both** push endpoints.
The proxy accepts only POSTs to `/api/v1/write` and `/loki/api/v1/push`;
Prometheus queries, Loki queries and administrative paths are unavailable
through it. The normal Prometheus and Loki host ports are replaced with
loopback bindings. Grafana continues querying the stores on the private Compose
network. The proxy follows Docker DNS when a store container is recreated.

This recipe requires Docker Compose **2.24.4 or later** and the bundled Loki
profile. Use the operator's firewall/VPN to restrict port 8443 to agent hosts.
It does not expose Grafana or replace its separate TLS proxy.

1. Obtain a certificate whose SAN names the DNS name agents will use, with a
   chain trusted by those agents. Use your existing certificate renewal service
   (DNS-based ACME works without an HTTP listener). Put the full certificate
   chain and unencrypted private key in the gitignored secrets directory:

   ```sh
   install -d -m 0700 secrets/push-tls
   install -m 0600 /path/to/fullchain.pem secrets/push-tls/fullchain.pem
   install -m 0600 /path/to/privkey.pem secrets/push-tls/privkey.pem
   # Prompts interactively; no password in history or process arguments.
   printf 'argus:%s\n' "$(openssl passwd -6)" > secrets/push-tls/htpasswd
   chmod 0600 secrets/push-tls/htpasswd
   ```

   The fixed agent username is `argus`. If you enabled
   [Prometheus authentication](security.md#requiring-a-password-for-prometheus),
   enter the **same password** here: Prometheus receives the agent's original
   Authorization header. Loki authentication is enforced by nginx, which strips
   that header before forwarding. The hash format for nginx is SHA-512 crypt;
   Prometheus' own configuration continues to use bcrypt.

   The proxy runs as uid/gid 101. As the host administrator, give that uid
   ownership of `secrets/push-tls` and its three files (`chown -R 101:101
   secrets/push-tls`). Keep the directory mode 0700 and the files mode 0600;
   do not make the private key readable by other host users. Certificate
   renewal must preserve these ownership and permission settings.

2. Set these values in the server's `.env`. Preserve any other profiles or
   overlays you already need, and put the TLS overlay last:

   ```dotenv
   COMPOSE_FILE=docker-compose.yml:docker-compose.tls.yml
   COMPOSE_PROFILES=loki
   ARGUS_PUSH_BIND=0.0.0.0:8443
   ```

   For source-mode installations, use
   `docker-compose.yml:docker-compose.source.yml:docker-compose.tls.yml`.
   The TLS overlay deliberately replaces the `PROMETHEUS_BIND` and `LOKI_BIND`
   values with `127.0.0.1:9090` and `127.0.0.1:3101`.

   ```sh
   docker compose config --quiet
   docker compose up -d
   ```

3. On each agent host, use the certificate's DNS name for **both** base URLs:

   ```dotenv
   ARGUS_PROMETHEUS_URL=https://argus-push.example:8443
   ARGUS_LOKI_URL=https://argus-push.example:8443
   ARGUS_PROMETHEUS_PASSWORD='the shared proxy password'
   ARGUS_LOKI_PASSWORD='the shared proxy password'
   ```

   Keep `.env` readable only by its owner (`chmod 0600 .env`). Single quotes
   preserve any literal `$` characters in passwords. Recreate the agent with
   `docker compose up -d` after changing credentials. Agents verify the server
   certificate using their image's system CA store; a private CA must be
   installed in a derived agent image. Never disable certificate verification.

   Loki credentials require an agent image built from this checkout or a release
   containing this feature. To try it before that release, build
   `docker build -t argus-agent:local agent/` from this repository on the agent
   host and set `ARGUS_AGENT_IMAGE=argus-agent:local` in the agent's `.env`.
   For Kubernetes, add `ARGUS_LOKI_PASSWORD` to the existing `argus-agent`
   Secret alongside the Prometheus password and use an updated agent image;
   the DaemonSet's `envFrom` reads both credentials. See
   [kubernetes.md](kubernetes.md).

4. Check the boundary from an agent host using a trusted certificate:

   ```sh
   # Each push path must reject missing credentials with 401.
   curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://argus-push.example:8443/api/v1/write
   curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://argus-push.example:8443/loki/api/v1/push
   # Query paths must return 404 even with credentials (curl prompts).
   curl -u argus -sS -o /dev/null -w '%{http_code}\n' https://argus-push.example:8443/api/v1/query
   ```

   An authenticated empty push is not a valid write and may return 400; check
   the agent's logs and fresh `up{job="node"}` samples plus host log entries
   in Grafana to verify real ingestion. Confirm ports 9090 and 3101 are
   unreachable from the agent host. The automated proxy test exercises valid
   credentials, rejected credentials, method/path restrictions, certificate
   trust and header forwarding against fixture upstreams:

   ```sh
   ARGUS_TEST_TLS=1 .venv/bin/pytest tests/test_push_security.py
   ```

After renewing certificates or changing `htpasswd`, reload the proxy with
`docker compose exec push-proxy nginx -s reload`. If renewal replaces a symlink
outside `secrets/push-tls`, copy the updated files into that directory first;
all certificate material must remain inside the mounted directory. Rotate both
agent passwords together with the proxy password and, if enabled, the
Prometheus password. The current agents share one identity; this is an
operator-managed installation, not per-agent access control.

The recipe uses nginx's
[HTTP Basic
authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)
and Alloy's
[Loki basic_auth endpoint
settings](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/#basic_auth).

For independent server-down notifications, configure an [external
heartbeat](heartbeat.md).
