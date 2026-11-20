# Plan: renovate-automerge

## What Sean asked for

"Ensure that all my repos that have renovate allow the renovate PRs to auto
merge", on the homelab-atlas model: every update, majors included, merges once
all checks pass, after a 3-day wait.

## What we found

- `main` has no required status checks, so GitHub's own auto-merge would merge
  before CI finished. Renovate will merge by itself instead (`platformAutomerge:
  false`), only once every check on the pull request has passed.
- Does a merge deploy? Only where the optional auto-deploy timer runs; it waits
  for the "Dashboards + config" check.

## What we'll change

1. `renovate.json`: turn on auto-merge for every update, majors included, the
   way homelab-atlas does it: `automerge: true`, squash merges,
   `platformAutomerge: false` (Renovate merges by itself on its next run, once
   every check on the pull request has passed); new versions wait 3 days before
   they are proposed (`minimumReleaseAge`, with `timestamp-optional` so a
   registry without release dates doesn't hold an update forever); security
   fixes and image rebuilds (digest updates) skip the wait. Check: Renovate's
   config validator passes, and a local Renovate dry run shows auto-merge on for
   ordinary updates.
2. Docs that say updates are merged by hand, or by Dependabot: README.md,
   GOVERNANCE.md, docs/dependencies.md. Say instead that Renovate merges updates
   once every check passes.
3. Record the job in `docs/` (pass map, decisions log, roadmap; created if
   missing).

## Kept manual

- Nothing: every update merges automatically.

Each exception is an earlier decision by the owner; to drop one, say so on this
pull request.

## Who's on it

Engineer, Security Officer, Auditor.

## Risks

- The owner's trial run in a sandbox before merging goes away for dependency
  updates. CI's "Dashboards + config" check is what catches breakage (it caught
  the Grafana 13.3.1 problem in #151).
- Renovate's schedule is unchanged, so updates still arrive once a week.

## Out of scope

Repository settings and branch rules (only the owner changes those), and the
workflows under `.github/workflows` (a leftover Dependabot auto-merge workflow
stays as it is).
