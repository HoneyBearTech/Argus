# Pass map

A short record of each piece of work on Argus: what shipped, or what a review found, and where to look.
Newest first. The reasons behind the choices are in the [decisions log](decisions-log.md); what is planned
next is in the [roadmap](roadmap.md).

| Date | Job | What shipped or was found | Where |
| --- | --- | --- | --- |
| 2026-11-20 | `argus-grafana-sh` | Grafana's entrypoint (`images/grafana/start.sh`) runs with `/bin/sh` instead of `/bin/bash`, because grafana/grafana 13.3.1 no longer ships bash; this was why Renovate's #151 failed "Dashboards + config", and it would have stopped Grafana starting after that update. A regression test checks the script needs only sh. Security review clear (the password check holds on both 13.2.4 and 13.3.1); code audit approved after one test fix. | #154 |
