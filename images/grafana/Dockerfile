# Argus Grafana: dashboards, datasources and alert rules baked in.
# Build context: repository root.
FROM grafana/grafana:13.2.2

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/argus/dashboards

ENV GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/argus/dashboards/overview/homelab-overview.json \
    GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false
