# Argus Grafana: dashboards, datasources and alert rules baked in.
# Build context: repository root.
FROM grafana/grafana:13.2.3@sha256:b28bae15e219c998fb0e0424ed724930cc61b1f61fb404d47c862f9a23f9e572

# Remove the bundled datasource plugins Argus doesn't use (everything but Prometheus and Loki):
# less code to patch, scan and expose. (The image doesn't get smaller: the files stay in the base
# layer.) CI's boot test checks that the two remain.
USER 0
RUN find /usr/share/grafana/data/plugins-bundled -mindepth 1 -maxdepth 1 \
        ! -name prometheus ! -name loki -exec rm -rf {} +
USER 472

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/argus/dashboards

ENV GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/argus/dashboards/overview/homelab-overview.json \
    GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false
