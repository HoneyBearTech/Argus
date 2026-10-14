#!/bin/bash
# Argus' entrypoint for Grafana: refuse to start without an admin password, then hand over to the
# image's own /run.sh. Grafana falls back to admin/admin when the password is empty, so an empty
# secrets/grafana_admin_password (its template is empty) must stop it here.
set -euo pipefail

if [ -n "${GF_SECURITY_ADMIN_PASSWORD__FILE:-}" ]; then
    password=$(cat -- "$GF_SECURITY_ADMIN_PASSWORD__FILE" 2> /dev/null || true)
else
    password=${GF_SECURITY_ADMIN_PASSWORD:-}
fi
if [ -z "${password//[[:space:]]/}" ]; then
    echo "Argus: no Grafana admin password: ${GF_SECURITY_ADMIN_PASSWORD__FILE:-GF_SECURITY_ADMIN_PASSWORD}" \
        "is empty or unreadable. Put a password in secrets/grafana_admin_password (mode 644)." >&2
    exit 1
fi
unset password

exec /run.sh "$@"
