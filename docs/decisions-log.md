# Decisions log

Why things in Argus are the way they are: each entry gives the decision, the reason, what was considered and
not done, and review findings that were declined, with why. Newest first. What shipped when is in the
[pass map](pass-map.md).

## 2026-11-20: Grafana's entrypoint runs under the image's own sh

Job `argus-grafana-sh` (#154).

**Decision.** `images/grafana/start.sh` starts with `#!/bin/sh`. In grafana/grafana 13.2.4 and 13.3.1,
`/bin/sh` is BusyBox ash (Alpine 3.24). The script still uses two features plain POSIX sh lacks,
`set -o pipefail` and `${var//...}`; ash has both, and a comment in the script says so.

**Why.** Grafana 13.3.1 (Renovate's #151) dropped `/bin/bash`, so the old entrypoint failed with
"no such file or directory" and Grafana never started. The CI step that expects the empty-password refusal
failed without a message.

**Checked.** On both images: empty, whitespace-only, missing and unreadable password files, and an empty or
whitespace-only environment password, are all refused before Grafana starts; a valid password gets through.

**Not done.** Installing bash in the image (more to maintain and scan); rewriting the script in strict POSIX
sh (not needed while the image's sh is ash, and it would change a security check for no gain); holding
Grafana at 13.2.4.

**Review findings.** The first regression test failed on a harmless comment mentioning bash and missed a
real `/bin/bash` command line; it now checks code lines only. Declined: nothing.
