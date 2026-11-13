# Argus documentation

Start with the [README](../README.md) for what Argus is, its dashboards and
alerts, and how to run it.

- **Document:** [Quick start](quick-start.md)
  - **For:** Running Argus on one machine and seeing your first dashboards in
    about ten minutes

- **Document:** [Architecture](architecture.md)
  - **For:** The components, how metrics, logs and alerts flow through them, and
    why

- **Document:** [Interfaces](interfaces.md)
  - **For:** Every port, push endpoint, environment variable, file and image
    Argus exposes or reads

- **Document:** [Server hardware (IPMI)](ipmi.md)
  - **For:** Reading each server's BMC (temperatures, fans, power supplies,
    batteries) for the Server Hardware dashboard and alerts

- **Document:** [Add-in GPUs on servers (hwmon)](hwmon.md)
  - **For:** Reading a server's add-in GPU (temperature, fan), which its BMC
    can't see, for the Server Hardware dashboard and the GPU hot alert

- **Document:** [Intel GPU load](intel-gpu.md)
  - **For:** How busy an Intel GPU's engines are (intel_gpu_top), on a server or
    through the agent's `intel-gpu` profile

- **Document:** [Kubernetes nodes](kubernetes.md)
  - **For:** Running the agent as a DaemonSet: node and container metrics and
    pod logs on the same dashboards as Docker hosts

- **Document:** [Steerhouse](steerhouse.md)
  - **For:** Connecting Steerhouse (Ansible web UI) for its three dashboards and
    alerts: metrics token, read-only database role over TLS, and re-porting its
    dashboards

- **Document:** [Upgrading](upgrading.md)
  - **For:** Moving to a new release, and rolling back

- **Document:** [Auto-deploy](auto-deploy.md)
  - **For:** Letting a server that runs from a checkout follow `main` by itself

- **Document:** [Verifying releases](verifying-releases.md)
  - **For:** Checking that images and release files came from this repository,
    unchanged

- **Document:** [Security requirements](security.md)
  - **For:** What Argus protects, and what it deliberately doesn't

- **Document:** [Assurance case](assurance-case.md)
  - **For:** The threat model, trust boundaries and why the security
    requirements are met

- **Document:** [Dependencies](dependencies.md)
  - **For:** How dependencies are chosen, pinned, tracked and patched

- **Document:** [Roadmap](roadmap.md)
  - **For:** What's planned for the next year, and what Argus will not do

Project policies live at the top of the repository:
[CONTRIBUTING.md](../CONTRIBUTING.md),
[GOVERNANCE.md](../GOVERNANCE.md), [SECURITY.md](../SECURITY.md),
[SUPPORT.md](../SUPPORT.md),
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) and [CHANGELOG.md](../CHANGELOG.md).

These documents change in the same pull request as the behaviour they describe.
If you find one that's
wrong, please [open an issue](https://github.com/HoneyBearTech/Argus/issues):
it's treated as a bug.
