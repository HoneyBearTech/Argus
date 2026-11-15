# Local model servers

Argus scrapes vLLM's native `/metrics` endpoint. Add each server to the
operator-owned `targets/vllm.json`:

```json
[
  {"targets": ["model-server.example.invalid:8000"]}
]
```

Keep this endpoint on the trusted monitoring network; never publish an
unauthenticated model API to the internet. Prometheus reloads the target list
without restarting. The Local Model Servers dashboard shows reachable servers,
models with exported `model_name` labels, running and queued requests, KV cache
occupancy and generated token throughput. An idle model still has a running
request gauge of zero, so it remains in the loaded-model inventory. Inventory
reflects exported metrics, rather than querying or changing the model server.

The integration uses the modern `vllm:kv_cache_usage_perc` metric, a fraction
from zero to one. Older vLLM releases exporting only
`vllm:gpu_cache_usage_perc` need upgrading. Cache occupancy measures allocated
KV blocks, not the model's total GPU memory; the existing GPUs dashboard shows
GPU memory. See the upstream
[vLLM metrics documentation](https://docs.vllm.ai/en/stable/design/metrics/).
Ollama and other servers without these metrics are not queried through their
administrative APIs.

## Generating dashboards

`scripts/generate_dashboards.py` is the source of the Local Model Servers
JSON. Common panel layout, datasource and field settings are defined once;
the `PANELS` definitions contain stable ids, titles, expressions and units.
Run `python scripts/generate_dashboards.py` after edits and commit both the
source and generated JSON. `--check` fails on output drift and runs in CI.
New repetitive dashboards can follow this pattern without requiring an
additional Jsonnet toolchain. Existing hand-maintained dashboards keep their
stable ids and UIDs.
