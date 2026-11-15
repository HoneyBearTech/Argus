#!/usr/bin/env python3
"""Generate repetitive dashboard panels from compact, reviewable definitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "dashboards" / "hosts" / "local-models.json"
DATASOURCE = {"type": "prometheus", "uid": "prometheus"}
# Stable ids are part of the dashboard interface; append new panels rather than renumbering.
PANELS = (
    (1, "Model servers up", 'up{job="vllm"}', "short"),
    (2, "Loaded models", 'count by (instance, model_name) (vllm:num_requests_running{job="vllm"})', "short"),
    (3, "Running requests", 'vllm:num_requests_running{job="vllm"}', "short"),
    (4, "Waiting requests", 'vllm:num_requests_waiting{job="vllm"}', "short"),
    (5, "KV cache used", 'vllm:kv_cache_usage_perc{job="vllm"}', "percentunit"),
    (6, "Generated tokens / second", 'rate(vllm:generation_tokens_total{job="vllm"}[5m])', "ops"),
)


def dashboard() -> dict[str, Any]:
    """Build the vLLM dashboard deterministically, sharing panel defaults."""
    return {
        "id": None,
        "uid": "argus-local-models",
        "title": "Local Model Servers",
        "description": "Which vLLM models are loaded, and are requests or KV cache capacity saturated?",
        "tags": ["argus", "models"],
        "editable": False,
        "schemaVersion": 41,
        "version": 1,
        "timezone": "browser",
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "panels": [
            {
                "id": panel_id,
                "title": title,
                "type": "timeseries",
                "datasource": DATASOURCE,
                "gridPos": {"h": 8, "w": 12, "x": ((panel_id - 1) % 2) * 12, "y": ((panel_id - 1) // 2) * 8},
                "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
                "targets": [
                    {
                        "refId": "A",
                        "expr": query,
                        "legendFormat": "{{instance}} {{model_name}}",
                        "datasource": DATASOURCE,
                    }
                ],
            }
            for panel_id, title, query, unit in PANELS
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Write generated JSON, or check that checked-in output is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    expected = json.dumps(dashboard(), indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text() != expected:
            print(f"Regenerate dashboard: {args.output}")
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
