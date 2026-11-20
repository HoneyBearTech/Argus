# Pass map

A short record of each piece of work on Argus: what shipped, or what a review found, and where to look.
Newest first. The reasons behind the choices are in the [decisions log](decisions-log.md); what is planned
next is in the [roadmap](roadmap.md).

| Date | Job | What shipped or was found | Where |
| --- | --- | --- | --- |
| 2026-11-20 | `argus-grafana-sh` | Grafana's entrypoint (`images/grafana/start.sh`) runs with `/bin/sh` instead of `/bin/bash`, because grafana/grafana 13.3.1 no longer ships bash; this was why Renovate's #151 failed "Dashboards + config", and it would have stopped Grafana starting after that update. A regression test checks the script needs only sh. Security review clear (the password check holds on both 13.2.4 and 13.3.1); code audit approved after one test fix. | #154 |
| 2026-11-20 | `renovate-automerge` | Renovate merges its pull requests itself once every check passes, majors included; new versions wait 3 days, security fixes and image rebuilds don't. Nothing kept manual (the `argus-*` images stay switched off, as before). `platformAutomerge` is false: `main` has no required checks, so Renovate merges itself once every check on the pull request passes. | #155 |
