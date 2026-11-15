# Notification channels

Discord remains the default. To select e-mail, an incoming Slack-compatible
webhook, or an ntfy topic instead, copy the new `secrets.example/` files into
`secrets/` without overwriting existing credentials, and add to `.env`:

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.notifications.yml
ARGUS_NOTIFICATION_CHANNEL=slack
```

Set `ARGUS_NOTIFICATION_CHANNEL` to `email`, `slack`, or `ntfy`. For Slack,
put the incoming webhook URL in `secrets/notification_endpoint`. For ntfy,
put a private HTTPS topic URL there, such as `https://ntfy.example.invalid/argus`.
The topic receives Grafana's JSON body, including alert status, labels and
annotations. Protect private topics with access controls at your ntfy server;
this recipe does not add bearer authentication. Do not use a public topic for
sensitive alert details.

For e-mail, additionally set:

```dotenv
ARGUS_EMAIL_ADDRESSES=operator@example.invalid;backup@example.invalid
ARGUS_SMTP_ENABLED=true
ARGUS_SMTP_HOST=smtp.example.invalid:587
ARGUS_SMTP_USER=argus
ARGUS_SMTP_FROM_ADDRESS=argus@example.invalid
```

Put the SMTP password in `secrets/smtp_password`. This recipe requires
STARTTLS and verifies the SMTP server certificate. Both secret files must
exist, even if unused by the chosen channel; empty templates suffice for an
unused file. Keep the secrets directory private to the operator and secret
files readable by Grafana (mode 644).

Run `docker compose config --quiet`, then recreate Grafana with
`docker compose up -d grafana`. The overlay replaces the default contact point
and policy with `Notifications`. In Grafana's Alerting contact points, send a
test notification and verify receipt before relying on alerts. Provisioned
settings survive container recreation. Remove the overlay and recreate Grafana
to restore the default Discord route.
