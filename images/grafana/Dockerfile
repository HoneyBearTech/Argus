# Argus Grafana: dashboards, datasources and alert rules baked in.
# Build context: repository root.
FROM grafana/grafana:13.3.0@sha256:488984b716c0862639f91a698adbe2862677a5a07bad42da5f03f3030883b205

# Plugins come only from this image. Grafana's background installer would otherwise download plugins
# from grafana.com at every start into the data volume, where they override the bundled ones: code that
# isn't in the signed, scanned image. So: no preinstalling, a plugin directory inside the image (which
# also ignores plugins an older Argus left in the volume), and of the bundled datasource plugins only the
# three Argus uses: Prometheus, Loki and PostgreSQL (Steerhouse's database). (The image doesn't get
# smaller: the removed files stay in the base layer.) CI's boot test checks that the three remain.
USER 0
RUN find /usr/share/grafana/data/plugins-bundled -mindepth 1 -maxdepth 1 \
        ! -name prometheus ! -name loki ! -name grafana-postgresql-datasource -exec rm -rf {} + \
    && mkdir -p /usr/share/grafana/data/plugins-argus \
    && chown 472:0 /usr/share/grafana/data/plugins-argus
USER 472

COPY provisioning /etc/grafana/provisioning
COPY dashboards /etc/argus/dashboards
# Refuses to start without an admin password, then runs the image's /run.sh.
COPY --chmod=0755 images/grafana/start.sh /argus-start.sh
ENTRYPOINT ["/argus-start.sh"]

ENV GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/etc/argus/dashboards/overview/homelab-overview.json \
    GF_PATHS_PLUGINS=/usr/share/grafana/data/plugins-argus \
    GF_PLUGINS_PREINSTALL_DISABLED=true \
    GF_USERS_ALLOW_SIGN_UP=false \
    GF_AUTH_ANONYMOUS_ENABLED=false
