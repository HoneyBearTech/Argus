# Argus documentation

Start with the [README](../README.md) for what Argus is, its dashboards and alerts, and how to run it.

| Document | For |
| --- | --- |
| [Quick start](quick-start.md) | Running Argus on one machine and seeing your first dashboards in about ten minutes |
| [Architecture](architecture.md) | The components, how metrics, logs and alerts flow through them, and why |
| [Interfaces](interfaces.md) | Every port, push endpoint, environment variable, file and image Argus exposes or reads |
| [Server hardware (IPMI)](ipmi.md) | Reading each server's BMC (temperatures, fans, power supplies, batteries) for the Server Hardware dashboard and alerts |
| [Add-in GPUs on servers (hwmon)](hwmon.md) | Reading a server's add-in GPU (temperature, fan), which its BMC can't see, for the Server Hardware dashboard and the GPU hot alert |
| [Intel GPU load](intel-gpu.md) | How busy an Intel GPU's engines are (intel_gpu_top), on a server or through the agent's `intel-gpu` profile |
| [Kubernetes nodes](kubernetes.md) | Running the agent as a DaemonSet: node and container metrics and pod logs on the same dashboards as Docker hosts |
| [Steerhouse](steerhouse.md) | Connecting Steerhouse (Ansible web UI) for its three dashboards and alerts: metrics token, read-only database role over TLS, and re-porting its dashboards |
| [Upgrading](upgrading.md) | Moving to a new release, and rolling back |
| [Auto-deploy](auto-deploy.md) | Letting a server that runs from a checkout follow `main` by itself |
| [Verifying releases](verifying-releases.md) | Checking that images and release files came from this repository, unchanged |
| [Security requirements](security.md) | What Argus protects, and what it deliberately doesn't |
| [Assurance case](assurance-case.md) | The threat model, trust boundaries and why the security requirements are met |
| [Dependencies](dependencies.md) | How dependencies are chosen, pinned, tracked and patched |
| [Roadmap](roadmap.md) | What's planned for the next year, and what Argus will not do |

Project policies live at the top of the repository: [CONTRIBUTING.md](../CONTRIBUTING.md),
[GOVERNANCE.md](../GOVERNANCE.md), [SECURITY.md](../SECURITY.md), [SUPPORT.md](../SUPPORT.md),
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) and [CHANGELOG.md](../CHANGELOG.md).

These documents change in the same pull request as the behaviour they describe. If you find one that's
wrong, please [open an issue](https://github.com/HoneyBearTech/Argus/issues): it's treated as a bug.
