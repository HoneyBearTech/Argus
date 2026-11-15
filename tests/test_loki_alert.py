"""Evaluate the shipped LogQL alert against a disposable Loki instance in CI."""

from __future__ import annotations

import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import promql_tests
import pytest

LOKI_URL = os.environ.get("ARGUS_TEST_LOKI_URL", "")


@pytest.mark.skipif(not LOKI_URL, reason="requires a disposable Loki; CI sets ARGUS_TEST_LOKI_URL")
def test_proxy_error_alert_uses_real_logql_evaluation() -> None:
    rule = promql_tests.load_rules()["argus-proxy-5xx"]
    query = next(item["model"]["expr"] for item in rule["data"] if item["refId"] == "A")
    condition = next(item["model"] for item in rule["data"] if item["refId"] == rule["condition"])
    evaluator = condition["conditions"][0]["evaluator"]
    operator = promql_tests.THRESHOLD_OPS[evaluator["type"]]
    alert_query = f"({query}) {operator} {evaluator['params'][0]}"
    now = time.time_ns()
    scenarios = [
        ("firing", "npm", "500", 21),
        ("firing", "npm", "503", 3),
        ("boundary", "npm", "502", 20),
        ("healthy", "npm", "500", 1),
        ("ignored-status", "npm", "404", 30),
        ("ignored-job", "other", "500", 30),
    ]
    streams = [
        {
            "stream": {"site": site, "job": job, "status": status},
            "values": [[str(now - 60_000_000_000 + index), f"synthetic line {index}"] for index in range(count)],
        }
        for site, job, status, count in scenarios
    ]
    request = Request(  # noqa: S310 - explicit disposable integration-test endpoint
        f"{LOKI_URL}/loki/api/v1/push",
        data=json.dumps({"streams": streams}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # CI supplies an isolated loopback HTTP server, never an operator's Loki.
    with urlopen(request, timeout=15) as response:  # noqa: S310 - URL is the explicit integration-test endpoint
        assert response.status == 204

    def evaluate(expression: str, timestamp: int) -> dict[str, float]:
        parameters = urlencode({"query": expression, "time": str(timestamp)})
        url = f"{LOKI_URL}/loki/api/v1/query?{parameters}"
        with urlopen(url, timeout=15) as response:  # noqa: S310 - same isolated test endpoint
            result = json.load(response)
        assert result["status"] == "success"
        return {sample["metric"]["site"]: float(sample["value"][1]) for sample in result["data"]["result"]}

    assert evaluate(query, now) == {"firing": 24, "boundary": 20, "healthy": 1}
    assert evaluate(alert_query, now) == {"firing": 24}
    # All pushed records lie outside this earlier evaluation's ten-minute window.
    assert evaluate(alert_query, now - 3_600_000_000_000) == {}
