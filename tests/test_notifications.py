"""Security contracts for optional provisioned notification channels."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(("channel", "kind"), [("email", "email"), ("slack", "slack"), ("ntfy", "webhook")])
def test_selected_channel_matches_policy(channel: str, kind: str) -> None:
    config = yaml.safe_load((ROOT / "deploy" / "notifications" / f"{channel}.yaml").read_text())
    point = config["contactPoints"][0]
    policies = yaml.safe_load((ROOT / "deploy" / "notifications" / "policies.yaml").read_text())
    assert point["name"] == policies["policies"][0]["receiver"]
    receiver = point["receivers"][0]
    assert receiver["type"] == kind
    assert receiver["disableResolveMessage"] is False
    if kind != "email":
        assert receiver["settings"]["url"] == "$__file{/run/secrets/notification_endpoint}"


def test_notification_overlay_keeps_credentials_in_files() -> None:
    config = yaml.safe_load((ROOT / "docker-compose.notifications.yml").read_text())
    grafana = config["services"]["grafana"]
    assert grafana["environment"]["GF_SMTP_STARTTLS_POLICY"] == "MandatoryStartTLS"
    assert "GF_SMTP_PASSWORD" not in grafana["environment"]
    assert grafana["environment"]["GF_SMTP_PASSWORD__FILE"] == "/run/secrets/smtp_password"  # noqa: S105
    assert grafana["secrets"] == ["notification_endpoint", "smtp_password"]
    assert "example.invalid" in (ROOT / "secrets.example" / "notification_endpoint").read_text()
