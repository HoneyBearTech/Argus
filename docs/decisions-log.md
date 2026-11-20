# Decisions log

Why things in Argus are the way they are: each entry gives the decision, the reason, what was considered and
not done, and review findings that were declined, with why. Newest first. What shipped when is in the
[pass map](pass-map.md).

## 2026-11-20: Renovate merges its own pull requests

Job `renovate-automerge` (#155).

**Decision.** Renovate merges its pull requests itself once every check passes,
majors included; new versions wait 3 days, security fixes and image rebuilds
don't, on the model another of the owner's stacks already uses. Kept manual: nothing kept manual
(the `argus-*` images stay switched off, as before). `platformAutomerge` is
false: `main` has no required checks, so Renovate merges itself once every check
on the pull request passes.

**Why.** The owner asked for every repo with Renovate to merge its updates
automatically (2026-11-20) and chose this model, majors included, over keeping
majors manual.

**Not done.** Repository settings and branch rules (owner only) and workflows
are unchanged. A group merges automatically only when every update in it may, so
each manual exception gets its own pull request.

**Review findings.** Fixed: stale docs that still promised a manual review or
named Dependabot, and (where it applied) exceptions that sat inside the update
group. None declined.

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
