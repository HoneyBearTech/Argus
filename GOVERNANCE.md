# Governance

Argus is a personal open-source project with a single maintainer. This document says how decisions are
made, who does what, who can reach the project's sensitive resources, and how the project carries on if
the maintainer can't.

## Decision model

Argus follows a "benevolent dictator" model: the maintainer makes the final call on every decision,
including what is in scope, which pull requests are merged, and when a release is made.

Decisions happen in the open wherever possible:

- **Bugs, features and questions** are discussed in [GitHub Issues](https://github.com/HoneyBearTech/Argus/issues).
  Anyone can open one or comment.
- **Changes** land only through pull requests to `main`, which is protected: every pull request must pass
  the required CI check, and it is squash-merged. The pull request description records what changed and
  why.
- **Direction** is published in the [roadmap](docs/roadmap.md), including what the project does not intend
  to do. Larger design choices are explained in the pull requests that make them.
- **Security reports** are handled privately, as described in [SECURITY.md](SECURITY.md), until a fix is
  released.

If you disagree with a decision, say so in the issue or pull request. The maintainer will explain the
reasoning, and may change course. Because the code is MIT-licensed, you can always fork it.

## Roles and responsibilities

| Role | Who | Responsibilities |
| --- | --- | --- |
| Maintainer | Sean Stoube ([@HoneyBearTech](https://github.com/HoneyBearTech)) | Triage issues; review and merge pull requests; keep CI, dependencies and documentation current; triage dependency and image vulnerability findings; respond to vulnerability reports as described in [SECURITY.md](SECURITY.md); cut and sign releases; enforce the [Code of Conduct](CODE_OF_CONDUCT.md); keep this document and the continuity arrangements below up to date. |
| Contributor | Anyone who opens an issue or pull request | Follow [CONTRIBUTING.md](CONTRIBUTING.md) (coding standards, tests, sign-off, no network details) and the [Code of Conduct](CODE_OF_CONDUCT.md); report vulnerabilities privately. |
| Security reporter | Anyone who reports a vulnerability | Report privately and allow time for a fix before disclosing, as described in [SECURITY.md](SECURITY.md). |

Automated tools also take part: Dependabot proposes updates to the upstream images, exporter images,
GitHub Actions and the Python check tools (the maintainer merges each by hand), and CI, CodeQL, the image
scan and OpenSSF Scorecard check every change.

## Access to sensitive resources

Who can change the code, releases and project settings, as of the date of this file's last change:

| Resource | Who has access | Through |
| --- | --- | --- |
| Repository administration (settings, branch protection, secrets, merging) | the maintainer (@HoneyBearTech) | GitHub account owner |
| Publishing images to GHCR | the release workflow, on a version tag pushed by the maintainer | GitHub Actions, short-lived `GITHUB_TOKEN` |
| Publishing images to Docker Hub | the release workflow, on a version tag; the maintainer | the `DOCKERHUB_TOKEN` repository secret (an access token limited to pushing); the maintainer's Docker Hub account |
| Signing images and release files | the release workflow, on a version tag | Sigstore keyless signing with the job's GitHub identity; no stored key |
| Signing version tags | the maintainer | personal SSH key (public half in [`.github/allowed_signers`](.github/allowed_signers)) |
| The list of internal names CI rejects | the maintainer; CI | the `ARGUS_FORBIDDEN_PATTERNS` repository secret |
| The OpenSSF Best Practices badge entry | the maintainer | GitHub sign-in |
| Security advisories and private vulnerability reports | the maintainer | GitHub |
| Automated changes | Dependabot (pull requests only; it can't merge, and the required check must pass) | GitHub |

There are no other collaborators. Workflows use the per-job `GITHUB_TOKEN`, read-only unless a job asks
for more, and repository secrets are only available to the workflows that name them, never to pull
requests from forks.

## Granting elevated access

Nobody gets write, maintain or admin access to the repository, or any of the resources above, without
this review:

1. The person has a public track record with the project: several merged pull requests of good quality
   over at least three months, and participation in reviews or issues.
2. Their identity is established: a GitHub account with history, two-factor authentication on, and a way
   for the maintainer to confirm who they are (for example a known employer, a long-standing open-source
   profile, or meeting in person).
3. The maintainer decides, records the decision and the role in a pull request that updates the tables in
   this file, and grants the least access that role needs.
4. Access is removed when someone steps back or is inactive for a year, also by a pull request here.

## The project's own secrets

The credentials the Argus project holds (not those of an Argus installation, which stay on the server in
`secrets/` and `.env`), and how they're handled:

- **What exists**: the maintainer's GitHub account and its recovery codes; the Docker Hub account and the
  access token stored as `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` repository secrets; the SSH key that signs
  tags; and the `ARGUS_FORBIDDEN_PATTERNS` repository secret, which isn't a credential but lists internal
  names that must not be published. Images and release files are signed keylessly (Sigstore), so there is
  no long-lived signing key.
- **Storage**: in the maintainer's password manager and GitHub encrypted secrets, never in the repository,
  CI logs, issues or pull requests. GitHub secret scanning with push protection blocks committed secrets,
  `.gitignore` excludes `.env`, `secrets/`, `targets/`, keys and certificates, and
  `scripts/check_dashboards.py` rejects private addresses and internal names in CI.
- **Access**: the maintainer only, plus the successor through the lockbox described under Continuity.
  The Docker Hub token is used only by the release workflow's publish job, which runs only for version
  tags pushed by the maintainer.
- **Rotation**: the Docker Hub token is replaced at least yearly; recovery codes are regenerated after use
  and at least yearly, and the lockbox updated; the tag-signing key is replaced (and
  `.github/allowed_signers` updated) if it may have been exposed. Any secret that might have leaked is
  revoked and replaced at once, and the incident handled as in [SECURITY.md](SECURITY.md).
- A new stored secret needs a reason, is scoped to the one workflow job that uses it, and is added to this
  section in the same pull request.

## Continuity

The project must be able to carry on, with issues opened and closed, changes accepted and releases made,
within a week of it being confirmed that the maintainer can no longer support it. To make that possible:

- **A lockbox**: the credentials needed to run the project are kept in a password-manager vault that a
  trusted person the maintainer has chosen can open through the password manager's **emergency access**,
  after a waiting period of a few days (short enough to act within the week). It holds the login and
  two-factor recovery codes of the GitHub account that owns the repository, access to that account's
  email address (GitHub asks it to confirm sign-ins from new devices), the Docker Hub login, and the SSH
  key that signs release tags. Release images are signed keylessly by GitHub Actions, so whoever controls
  the repository can keep publishing verifiable releases.
- **A succession note**, kept with the maintainer's personal papers and referenced from the lockbox, gives
  that person the right to continue the project or to hand it to a new maintainer.
- Everything else needed to keep working on the project is in this repository: the code, the CI
  configuration, the release process and the documentation.

Names and credentials are deliberately not published here. If the maintainer becomes unable to continue,
the successor will announce it in a pinned issue and update this file.

This is still a one-person project, so its "bus factor" is 1: these arrangements keep the project from
being stranded, but they don't replace a second active maintainer. People who contribute regularly may be
invited to become maintainers; this document will be updated when that happens.
