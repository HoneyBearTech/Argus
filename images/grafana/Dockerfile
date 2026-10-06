# Argus Grafana: dashboards, datasources and alert rules baked in.
# Build context: repository root.
FROM grafana/grafana:13.2.3@sha256:b28bae15e219c998fb0e0424ed724930cc61b1f61fb404d47c862f9a23f9e572

# Plugins come only from this image. Grafana's background installer would otherwise download plugins
# from grafana.com at every start into the data volume, where they override the bundled ones: code that
# isn't in the signed, scanned image. So: no preinstalling, a plugin directory inside the image (which
# also ignores plugins an older Argus left in the volume), and of the bundled datasource plugins only the
# two Argus uses, Prometheus and Loki. (The image doesn't get smaller: the removed files stay in the base
# layer.) CI's boot test checks that the two remain.
USER 0
RUN find /usr/share/grafana/data/plugins-bundled -mindepth 1 -maxdepth 1 \
        ! -name prometheus ! -name loki -exec rm -rf {} + \
    && mkdir -p /usr/share/grafana/data/plugins-argus \
    && chown 472:0 /usr/share/grafana/data/plugins-argus
USER 472

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/argus/dashboards

ENV GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/argus/dashboards/overview/homelab-overview.json \
    GF_PATHS_PLUGINS=/usr/share/grafana/data/plugins-argus \
    GF_PLUGINS_PREINSTALL_DISABLED=true \
    GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false
