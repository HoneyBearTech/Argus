# Kubernetes nodes

A Kubernetes node runs the same agent image as a Docker host, with a second configuration built into it,
[`agent/kubernetes.alloy`](../agent/kubernetes.alloy). One pod per node (a DaemonSet) pushes:

| What | From | Labels the dashboards use |
| --- | --- | --- |
| Node metrics (Host Health) | embedded node_exporter on the node's `/proc`, `/sys` and root filesystem | `job="node"`, `host` = the node's name |
| Container metrics (Docker Containers) | the node's own kubelet (`/metrics/cadvisor`) | `job="cadvisor"`, `name` = `<namespace>/<container>`, plus `namespace`, `pod`, `image` |
| Pod logs (Logs) | the node's `/var/log/pods` files | `job="kubernetes"`, `container` = `<namespace>/<container>`, plus `namespace`, `pod`, `stream` |

A container's `name` stays the same across pod restarts and rollouts, so its history and the "Container
restarting repeatedly" alert follow it. The kubelet counts network traffic per pod, not per container: it shows as
a row named `<namespace>/<pod>` with only the network columns filled. The pods' own volumes (everything under the
kubelet's and the container runtime's directories) aren't listed as the node's disks.

Nothing changes on the Argus server: the agent pushes to the same Prometheus and Loki as every Docker host, with
the same `argus` user if Prometheus requires a password. It was built on k3s with containerd; it reads nothing
specific to k3s except that its runtime mounts (`/run/k3s/…`) are left out of the disk list.

## What it needs

- **A Secret** with `ARGUS_PROMETHEUS_URL`, `ARGUS_LOKI_URL` and, if Prometheus requires one,
  `ARGUS_PROMETHEUS_PASSWORD`. Create it in the cluster, never in git:

  ```sh
  kubectl create namespace argus
  kubectl -n argus create secret generic argus-agent \
    --from-literal=ARGUS_PROMETHEUS_URL=http://argus-server:9090 \
    --from-literal=ARGUS_LOKI_URL=http://argus-server:3101 \
    --from-file=ARGUS_PROMETHEUS_PASSWORD=/dev/stdin   # type or paste it, Enter, Ctrl-D
  ```

- **RBAC**: `get` on `nodes/metrics` (the kubelet's cAdvisor endpoint, checked by the kubelet through the API
  server) and `get`, `list`, `watch` on `pods` (to find the log files of the pods on its node). Nothing else.
- **Host access**, for the same reasons as on a Docker host ([security](security.md#the-agents-exceptions)):
  the node's network and PID namespaces, `/` mounted read-only as `/rootfs` and `/sys` read-only; root with
  only `DAC_OVERRIDE` (pod log files belong to root, mode 0640), a read-only root filesystem, not privileged.
  Unlike a Docker host it gets **no container runtime socket**: container metrics come from the kubelet and logs
  from files, so the agent can't start or change containers.
- **Tolerations** for every taint, so it also runs on control-plane nodes.
- Its Alloy UI listens on `127.0.0.1:12345` only (it shares the node's network).

## Example

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: argus-agent
  namespace: argus
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: argus-agent
rules:
  - apiGroups: [""]
    resources: [nodes/metrics]
    verbs: [get]
  - apiGroups: [""]
    resources: [pods]
    verbs: [get, list, watch]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: argus-agent
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: argus-agent
subjects:
  - kind: ServiceAccount
    name: argus-agent
    namespace: argus
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: argus-agent
  namespace: argus
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: argus-agent
  updateStrategy:
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app.kubernetes.io/name: argus-agent
    spec:
      serviceAccountName: argus-agent
      hostNetwork: true
      hostPID: true
      dnsPolicy: ClusterFirstWithHostNet
      tolerations:
        - operator: Exists
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: agent
          # Pin a release by digest: ghcr.io/honeybeartech/argus-agent:<version>@sha256:<digest>
          image: ghcr.io/honeybeartech/argus-agent:0.9.0
          args:
            - run
            - /etc/alloy/kubernetes.alloy
            - --storage.path=/var/lib/alloy/data
            - --server.http.listen-addr=127.0.0.1:12345
          env:
            - name: ARGUS_HOST
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: ARGUS_NODE_IP
              valueFrom:
                fieldRef:
                  fieldPath: status.hostIP
          envFrom:
            - secretRef:
                name: argus-agent
          securityContext:
            runAsUser: 0
            runAsGroup: 0
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: [ALL]
              add: [DAC_OVERRIDE]
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              memory: 384Mi
          volumeMounts:
            - name: rootfs
              mountPath: /rootfs
              readOnly: true
              mountPropagation: HostToContainer
            - name: sys
              mountPath: /sys
              readOnly: true
            - name: data
              mountPath: /var/lib/alloy/data
      volumes:
        - name: rootfs
          hostPath:
            path: /
        - name: sys
          hostPath:
            path: /sys
        # Only Alloy's write-ahead log and log positions. Lost when the pod is replaced: it then re-reads at most
        # the last hour of each log file, and Loki ignores lines it already has.
        - name: data
          emptyDir: {}
```

## Checking it

Each node should appear within a minute on **Host Health** (its own row, `up{job="node"}` 1), on **Docker
Containers** (its pods' containers as `<namespace>/<container>`) and in **Logs** (Host = the node). If a node's
containers are missing, the agent's log (`kubectl -n argus logs <pod>`) names the kubelet scrape's error: a
`403` means the RBAC rule for `nodes/metrics` is missing; a certificate error means the kubelet's serving
certificate isn't signed by the cluster CA in the pod's service account (k3s signs it so; some distributions
don't, and need their kubelet CA mounted instead).
