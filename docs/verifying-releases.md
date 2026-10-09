# Verifying releases

Every Argus release is built and published by the [`release.yml`](../.github/workflows/release.yml)
workflow when a version tag is pushed. You can check that what you run came from that workflow, unchanged:

- the **images** (on GHCR and Docker Hub) are signed with [cosign](https://docs.sigstore.dev/)
  "keylessly": the signature is tied to the workflow's GitHub identity through
  [Sigstore](https://www.sigstore.dev/), so there is no long-lived signing key to steal, and every
  signature is recorded in the public Rekor transparency log;
- the images carry an **SBOM** (software bill of materials) and **SLSA provenance** (how and from which
  commit they were built) as attestations;
- each GitHub Release has a source archive, `images.txt` (the image digests) and `SHA256SUMS`, which is
  signed the same way (`SHA256SUMS.sigstore.json`), plus **SLSA build provenance** for those files
  (`argus-<version>.provenance.sigstore.json`, also stored by GitHub);
- the **version tag** in git is signed with the maintainer's SSH key.

This applies to releases after 0.1.0; v0.1.0 was published before signing was added. You need
[cosign](https://docs.sigstore.dev/cosign/system_config/installation/) 3.0 or later: releases are signed
with cosign 3, which stores image signatures as Sigstore bundles that cosign 2 doesn't find (it reports
"no signatures found"). The examples use
version 0.4.1; substitute the one you run.

## The images

```sh
for image in argus-grafana argus-prometheus argus-blackbox argus-loki argus-agent; do
  cosign verify "ghcr.io/honeybeartech/${image}:0.4.1" \
    --certificate-identity-regexp '^https://github\.com/HoneyBearTech/Argus/\.github/workflows/release\.yml@refs/tags/v' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
done
```

For Docker Hub, use `docker.io/honeybeartech/${image}:0.4.1`; the identity is the same. cosign prints the
verified signatures, including the commit and tag they were built from.

A tag such as `0.4.1` can be moved, a digest can't: for the strongest guarantee, pin the digests from the
release's `images.txt` (after verifying it, below), for example
`ARGUS_AGENT_IMAGE=ghcr.io/honeybeartech/argus-agent@sha256:…`.

To see the SBOM and the provenance:

```sh
docker buildx imagetools inspect ghcr.io/honeybeartech/argus-grafana:0.4.1 --format '{{ json .SBOM }}'
docker buildx imagetools inspect ghcr.io/honeybeartech/argus-grafana:0.4.1 --format '{{ json .Provenance }}'
```

## The release files

Download `SHA256SUMS`, `SHA256SUMS.sigstore.json`, `images.txt` and the source archive from the
[release page](https://github.com/HoneyBearTech/Argus/releases), then:

```sh
cosign verify-blob SHA256SUMS --bundle SHA256SUMS.sigstore.json \
  --certificate-identity-regexp '^https://github\.com/HoneyBearTech/Argus/\.github/workflows/release\.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum -c SHA256SUMS
```

The first command proves `SHA256SUMS` came from the release workflow; the second, that the archive and
`images.txt` match it.

## Build provenance

With the [GitHub CLI](https://cli.github.com/), check that a downloaded release file was built by this
repository's release workflow:

```sh
gh attestation verify argus-0.4.1.tar.gz --repo HoneyBearTech/Argus \
  --signer-workflow HoneyBearTech/Argus/.github/workflows/release.yml
```

It prints the verified attestation, including the commit and workflow run. To verify offline, add
`--bundle argus-0.4.1.provenance.sigstore.json`. Every file listed in `SHA256SUMS` is covered.

## The git tag

The maintainer signs version tags with an SSH key whose public half is in
[`.github/allowed_signers`](../.github/allowed_signers):

```sh
git clone https://github.com/HoneyBearTech/Argus.git && cd Argus
git -c gpg.ssh.allowedSignersFile=.github/allowed_signers tag -v v0.4.1
```

It should print `Good "git" signature for 31805425+HoneyBearTech@users.noreply.github.com`. Check
`.github/allowed_signers` against the key published at <https://github.com/HoneyBearTech.keys> rather than
trusting the copy in the same checkout alone.

## If a check fails

Don't run that image or file. Pull or download it again; if the check still fails, report it privately as
a security issue ([SECURITY.md](../SECURITY.md)).
