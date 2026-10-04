# Argus Grafana: dashboards, datasources and alert rules baked in.
# Build context: repository root.
FROM grafana/grafana:13.2.3@sha256:b28bae15e219c998fb0e0424ed724930cc61b1f61fb404d47c862f9a23f9e572

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/argus/dashboards

ENV GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/argus/dashboards/overview/homelab-overview.json \
    GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false
