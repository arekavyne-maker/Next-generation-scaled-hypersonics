# NGSH Helm chart

Platform-agnostic Helm chart for the NGSH platform: the six backend services
and the operator console, deployed as plain Kubernetes objects.

There are **no cloud-provider CRDs, no provider-specific service fields, and
no provider SDKs** in this chart. The same chart installs into AWS GovCloud,
Azure Government, an on-prem IL6 enclave, or a disconnected edge annex — only
the values change.

---

## 1. Contents

| Path | Purpose |
|---|---|
| `Chart.yaml` | Chart metadata (`ngsh`, 0.1.0, appVersion 0.1.0) |
| `values.yaml` | All values, plus the four deployment profiles |
| `values.schema.json` | JSON Schema (draft-07) that Helm validates values against |
| `templates/_helpers.tpl` | Naming, labels, profile merge, per-service resolution |
| `templates/NOTES.txt` | Post-install notes, warnings, and verification commands |
| `templates/serviceaccount.yaml` | Runtime service account + minimal Role/RoleBinding |
| `templates/serviceaccount-token.yaml` | Workload-identity service account + projected-token RBAC |
| `templates/configmap.yaml` | Non-secret configuration as JSON |
| `templates/secret.yaml` | Templated secrets from `values.secrets` (`stringData`) |
| `templates/service.yaml` | One ClusterIP Service per platform service |
| `templates/deployment.yaml` | One Deployment per platform service |
| `templates/pvc.yaml` | PersistentVolumeClaims for services that ask for storage |
| `templates/hpa.yaml` | HorizontalPodAutoscaler (opt-in) |
| `templates/pdb.yaml` | PodDisruptionBudget (opt-in) |
| `templates/networkpolicy.yaml` | Default-deny ingress/egress per service |
| `templates/ingress.yaml` | Optional internal ingress for the console |
| `templates/tests/test-health.yaml` | `helm test` pod that probes `/healthz` |

---

## 2. Install

```bash
helm install ngsh deploy/helm/ngsh \
  --namespace ngsh --create-namespace \
  --set deploymentProfiles.activeProfile=il5 \
  --set global.imageRegistry=registry.example.gov
```

`global.imageRegistry` is a **prefix**, not a replacement. With
`global.imageRegistry=registry.example.gov` and the default
`services.fabric.image.repository=ngsh/fabric-service`, the rendered image is
`registry.example.gov/ngsh/fabric-service:0.1.0`. A per-service
`services.<name>.image.registry` overrides the global prefix.

Render without installing:

```bash
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=local
```

---

## 3. The four deployment profiles

A profile is a **sparse overlay** on the base values. Only the keys a profile
mentions differ; everything else is inherited. Exactly one profile is active
at a time, selected by `deploymentProfiles.activeProfile`.

| | `local` | `il5` | `il6` | `edge` |
|---|---|---|---|---|
| Setting | developer laptop / CI | accredited cloud enclave | on-prem classified enclave | segregated single-node annex |
| Zone label | `local-dev` | `accredited-enclave` | `classified-enclave` | `edge-annex` |
| Zone classification level | `UNCLASSIFIED` | `CUI` | `SECRET` | `CUI` (capped) |
| Replicas (fabric) | 1 | 3 (HPA-managed) | 2 | 1 |
| Replicas (ontology/policy/audit/thread) | 1 | 2 | 2 | 1 |
| Replicas (ingest) | 1 | 1 | 1 | 1 |
| Replicas (console) | 1 | 2 | 1 | 1 |
| `hostNetwork` | `false` | `false` | **`true`** | `false` |
| `dnsPolicy` | `ClusterFirst` | `ClusterFirst` | **`ClusterFirstWithHostNet`** | `ClusterFirst` |
| Node affinity | none | zone spread | **required pod anti-affinity per host** | `nodeSelector: ngsh.io/node-class=edge` |
| Storage class | cluster default | `ngsh-encrypted-retain` | **`ngsh-classified-local`** | cluster default (node-local) |
| Access modes | `ReadWriteOnce` | `ReadWriteOnce` | `ReadWriteOnce` | **`ReadWriteOnce`** |
| Persistence | off | on | on | on |
| HPA | off | **on** (5 request-serving services) | off | off |
| PodDisruptionBudget | off | **on** | **on** | off |
| Ingress | off | **on**, class `internal` | off | off |
| External egress | denied | **allowed to approved CIDRs** | denied | denied |
| OTel collector egress | allowed | allowed | allowed | **denied (buffered locally)** |
| Topology spread | none | **across zones** | none | none |

### Why IL6 and edge genuinely differ

Both are constrained environments, and they are constrained in opposite
directions.

**IL6 is a classified enclave that is big enough to be redundant.** It runs on
the hosts' own interfaces (`hostNetwork: true`), so the enclave's own network
monitoring and egress control applies to the platform directly rather than to
a virtual network layered on top. It requires strict pod anti-affinity so no
two replicas of a service share a host — a host loss must not take a service
with it. It stores on a dedicated classified-local StorageClass, never on
shared infrastructure. It runs no ingress controller at all: the console is
reached through an operator jump host on the management segment. It disables
autoscaling, because a classified enclave runs on planned capacity.

**Edge is a single node that is physically disconnected.** It runs exactly one
replica of everything, on a node selected by an edge-hardware label. It does
**not** use host networking: the annex sits behind the site firewall on its
own routed segment, and host networking would put the platform's ports on the
physical interface. It has no PDB, because a budget on one replica on one
node would block every voluntary eviction and make node maintenance
impossible. It has no HPA, because there is nowhere to scale to. It has no
external egress and no collector egress: telemetry is buffered locally and
flushed with the next store-and-forward reconciliation.

### Render each profile

```bash
for p in local il5 il6 edge; do
  helm template ngsh deploy/helm/ngsh \
    --set deploymentProfiles.activeProfile=$p \
    > /tmp/ngsh-$p.yaml
done
```

Inspect the differences:

```bash
# IL6 uses host networking
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=il6 \
  | grep -n "hostNetwork"

# Edge selects edge hardware and runs a single replica
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=edge \
  | grep -n -A2 "nodeSelector"

# Edge has no ingress and no disruption budget
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=edge \
  | grep -cE "kind: (Ingress|PodDisruptionBudget)"
```

---

## 4. Values reference

### 4.1 Top level

| Key | Type | Default | Description |
|---|---|---|---|
| `global` | map | see below | Cluster-wide settings |
| `nameOverride` | string | `""` | Replaces the chart name in resource names |
| `fullnameOverride` | string | `""` | Replaces the whole generated name |
| `deploymentProfiles.activeProfile` | enum | `local` | `local` \| `il5` \| `il6` \| `edge` |
| `deploymentProfiles.profiles` | map | 4 profiles | The profile overlays |
| `serviceAccount` | map | see below | Runtime identity |
| `existingSecret` | string | `""` | Use a pre-provisioned Secret instead of rendering one |
| `config` | map | see below | Non-secret platform configuration |
| `secrets` | map | placeholders | Secret values (see §7) |
| `ingress` | map | disabled | Console ingress |
| `networkPolicy` | map | enabled | Default-deny policies |
| `pod` | map | see below | Pod-level defaults |
| `persistence` | map | disabled | Default storage settings |
| `autoscaling` | map | disabled | Default HPA settings |
| `podDisruptionBudget` | map | disabled | Default PDB settings |
| `tests` | map | enabled | `helm test` pod |
| `services` | map | 7 services | Per-service configuration |

### 4.2 `global`

| Key | Type | Default | Description |
|---|---|---|---|
| `global.imageRegistry` | string | `""` | Registry prefix for all images. Per-service `image.registry` wins. |
| `global.imagePullSecrets` | list | `[]` | Pull secret names. |
| `global.imagePullPolicy` | enum | `IfNotPresent` | `Always` \| `IfNotPresent` \| `Never` |
| `global.commonLabels` | map | `{}` | Added to every object. |
| `global.commonAnnotations` | map | `{}` | Added to every object. |
| `global.environment` | string | `dev` | Environment name (`dev`, `prod`, `field`). |
| `global.zone` | string | `local-dev` | Zone label: `central-fabric`, `accredited-enclave`, `classified-enclave`, `edge-annex`. |
| `global.storageClass` | string | `""` | Default StorageClass when a service names none. |

### 4.3 `serviceAccount`

| Key | Type | Default | Description |
|---|---|---|---|
| `serviceAccount.create` | bool | `true` | Create the service account. |
| `serviceAccount.name` | string | `""` | Defaults to the release fullname. |
| `serviceAccount.annotations` | map | `{}` | Provider-specific annotations, if any. |
| `serviceAccount.automountServiceAccountToken` | bool | `false` | The default token is never mounted. |
| `serviceAccount.workloadIdentity.enabled` | bool | `false` | Use the dedicated workload-identity service account. |
| `serviceAccount.workloadIdentity.audience` | string | `ngsh.example.gov` | Audience of the projected token. |
| `serviceAccount.workloadIdentity.expirationSeconds` | int | `3600` | Projected token lifetime (600–86400). |
| `serviceAccount.workloadIdentity.tokenMountPath` | string | `/var/run/secrets/ngsh` | Where the token is mounted. |
| `serviceAccount.workloadIdentity.annotations` | map | `{}` | Identity-provider annotations (supplied by the operator). |
| `serviceAccount.workloadIdentity.rbac.create` | bool | `true` | Create the Role/RoleBinding. |
| `serviceAccount.workloadIdentity.rbac.rules` | list | `[]` | Extra rules for the workload-identity account. |

### 4.4 `config` (non-secret)

| Key | Type | Default | Description |
|---|---|---|---|
| `config.tenant` | string | `ngsh` | Tenant key. Every query is tenant-scoped. |
| `config.classificationLevel` | enum | `UNCLASSIFIED` | Zone handling caveat: `UNCLASSIFIED`, `CUI`, `CUI//REL`, `CUI//FOUO`, `RESTRICTED`, `SECRET`, `TOP SECRET`. |
| `config.identityProvider` | enum | `stub` | `stub` (development actor) or `piv` (PIV/ICAM federation). The platform **refuses** `stub` outside the `local` and `edge` profiles, so the `il5` and `il6` profiles set `piv`. |
| `config.logLevel` | enum | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` |
| `config.logFormat` | enum | `json` | `json` \| `text` |
| `config.graphBackend` | enum | `postgres` | `postgres` \| `neptune` \| `janusgraph` |
| `config.graphNamespace` | string | `graph` | Graph namespace/schema. |
| `config.otel.endpoint` | string | `http://otel-collector.observability.svc.cluster.local:4317` | OTLP destination. |
| `config.otel.protocol` | enum | `grpc` | `grpc` \| `http/protobuf` |
| `config.otel.tlsInsecure` | bool | `false` | Disable TLS (development only). |
| `config.otel.resourceAttributes` | map | `{}` | Extra OTel resource attributes, e.g. `program: NGSH-SHY`. |
| `config.extra` | map | `{}` | Free-form non-secret configuration. |

### 4.5 `ingress`

| Key | Type | Default | Description |
|---|---|---|---|
| `ingress.enabled` | bool | `false` | **Disabled by default.** |
| `ingress.className` | string | `""` | Must be an **internal** class in an accredited zone. |
| `ingress.annotations` | map | `{}` | Controller annotations. |
| `ingress.hosts[].host` | string | `ngsh.example.gov` | Hostname. |
| `ingress.hosts[].paths[].path` | string | `/` | Path. |
| `ingress.hosts[].paths[].pathType` | enum | `Prefix` | `Exact` \| `Prefix` \| `ImplementationSpecific` |
| `ingress.hosts[].paths[].service` | enum | `web` | Which service serves the path. |
| `ingress.tls` | list | `[]` | TLS blocks. |

### 4.6 `networkPolicy`

| Key | Type | Default | Description |
|---|---|---|---|
| `networkPolicy.enabled` | bool | `true` | Render default-deny policies. |
| `networkPolicy.allowIngressController` | bool | `true` | Allow the ingress-controller namespace. |
| `networkPolicy.ingressControllerNamespace` | string | `ingress` | Namespace of the ingress controller. |
| `networkPolicy.database.enabled` | bool | `true` | Allow egress to the datastore. |
| `networkPolicy.database.namespaceSelector` | map | `{}` | Empty = any namespace. |
| `networkPolicy.database.port` | int | `5432` | Datastore port. |
| `networkPolicy.otel.enabled` | bool | `true` | Allow egress to the collector. The edge profile turns this off. |
| `networkPolicy.otel.namespaceSelector` | map | `{}` | Empty = any namespace. |
| `networkPolicy.otel.port` | int | `4317` | Collector OTLP port. |
| `networkPolicy.externalEgress` | bool | `false` | Allow egress outside the cluster. |
| `networkPolicy.externalEgressCIDRs` | list | `[]` | Allowed CIDRs. Empty with `externalEgress: true` means `0.0.0.0/0`. |
| `networkPolicy.extraIngress` | list | `[]` | Raw extra ingress rules, applied to every service. |
| `networkPolicy.extraEgress` | list | `[]` | Raw extra egress rules, applied to every service. |

### 4.7 `pod`

| Key | Type | Default | Description |
|---|---|---|---|
| `pod.hostNetwork` | bool | `false` | IL6 uses `true`. |
| `pod.dnsPolicy` | string | `""` | Empty = `ClusterFirst`, or `ClusterFirstWithHostNet` when `hostNetwork` is true. |
| `pod.priorityClassName` | string | `""` | Must already exist in the cluster. |
| `pod.terminationGracePeriodSeconds` | int | `30` | Graceful shutdown window. |
| `pod.deploymentStrategy` | map | `{}` | Empty = RollingUpdate 1/0. |
| `pod.securityContext` | map | non-root 10001, `RuntimeDefault` seccomp | Pod-level security context. |
| `pod.containerSecurityContext` | map | no privilege escalation, read-only rootfs, drop ALL | Container security context. |
| `pod.nodeSelector` | map | `{}` | Default node selector. |
| `pod.tolerations` | list | `[]` | Default tolerations. |
| `pod.affinity` | map | `{}` | Default affinity. The IL6 profile sets pod anti-affinity here. |
| `pod.topologySpreadConstraints` | list | `[]` | Default spreading. |
| `pod.extraPodAnnotations` / `extraPodLabels` | map | `{}` | Merged into every pod. |
| `pod.extraVolumes` / `extraVolumeMounts` | list | `[]` | Merged into every pod. |

### 4.8 `persistence`, `autoscaling`, `podDisruptionBudget` (defaults)

| Key | Type | Default | Description |
|---|---|---|---|
| `persistence.enabled` | bool | `false` | Provision a PVC. |
| `persistence.size` | string | `8Gi` | Requested volume size. |
| `persistence.storageClass` | string | `""` | Empty = cluster default. |
| `persistence.accessModes` | list | `[ReadWriteOnce]` | PVC access modes. |
| `persistence.existingClaim` | string | `""` | Use a pre-provisioned claim; no PVC is rendered. |
| `persistence.mountPath` | string | `/var/lib/ngsh` | Mount path in the container. |
| `autoscaling.enabled` | bool | `false` | Render an HPA. |
| `autoscaling.minReplicas` / `maxReplicas` | int | `2` / `6` | HPA bounds. |
| `autoscaling.targetCPUUtilizationPercentage` | int | `75` | CPU target. |
| `autoscaling.targetMemoryUtilizationPercentage` | int/null | `null` | Memory target. |
| `autoscaling.annotations` | map | `{}` | HPA annotations. |
| `autoscaling.behavior` | map | `{}` | HPA scaling behaviour. |
| `podDisruptionBudget.enabled` | bool | `false` | Render a PDB. |
| `podDisruptionBudget.minAvailable` | int/string | `1` | Minimum available pods. |
| `podDisruptionBudget.maxUnavailable` | int/string/null | `null` | Alternative to `minAvailable`. |
| `podDisruptionBudget.annotations` | map | `{}` | PDB annotations. |

### 4.9 `tests`

| Key | Type | Default | Description |
|---|---|---|---|
| `tests.enabled` | bool | `true` | Render the `helm test` pod. |
| `tests.image.registry` / `repository` / `tag` | string | `curlimages/curl:8.10.1` | Probe image. |
| `tests.image.pullPolicy` | enum | `""` | Falls back to `global.imagePullPolicy`. |
| `tests.service` | enum | `ontology` | Which service to probe. |
| `tests.path` | string | `/healthz` | Health path. |
| `tests.timeoutSeconds` | int | `10` | Probe timeout. |

### 4.10 `services.<name>`

One block per service: `ontology`, `fabric`, `policy`, `audit`, `thread`,
`ingest`, `web`.

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `true` | Deploy the service. |
| `name` | string | e.g. `fabric-service` | Service name; also the container name and the OTel `service.name`. |
| `port` | int | 8081–8086, 8080 | Container port. |
| `upstreams` | list | see `values.yaml` | Services this one calls. The chart renders an `NGSH_<KEY>_URL` env var for each. |
| `replicaCount` | int | `1` | Replicas. Omitted from the Deployment when an HPA is active. |
| `image.registry` | string | `""` | Overrides `global.imageRegistry`. |
| `image.repository` | string | `ngsh/<name>` | Image repository. |
| `image.tag` | string | `""` | Defaults to `appVersion`. |
| `image.pullPolicy` | enum | `""` | Falls back to `global.imagePullPolicy`. |
| `resources` | map | per service | Requests and limits. |
| `probes.liveness` | map | `/healthz` | Liveness probe. |
| `probes.readiness` | map | `/readyz` | Readiness probe. |
| `probes.startup` | map | `/healthz` | Startup probe. |
| `env` | list | `[]` | Extra environment variables. |
| `envFrom` | list | `[]` | Extra `envFrom` sources. |
| `extraEnv` | list | `[]` | Extra environment variables (alias of `env`). |
| `autoscaling.*` | map | `null` | Per-service HPA overrides; `null` inherits. |
| `podDisruptionBudget.*` | map | `null` | Per-service PDB overrides; `null` inherits. |
| `persistence.*` | map | `null` | Per-service storage overrides; `null` inherits. |
| `networkPolicy.enabled` | bool/null | `null` | Per-service policy toggle. |
| `networkPolicy.extraIngress` / `extraEgress` | list | `[]` | Per-service extra rules. |
| `nodeSelector` | map | `{}` | Per-service node selector; non-empty overrides `pod.nodeSelector`. |
| `tolerations` | list | `[]` | Per-service tolerations. |
| `affinity` | map | `{}` | Per-service affinity. |
| `topologySpreadConstraints` | list | `[]` | Per-service spreading. |
| `podAnnotations` / `podLabels` | map | `{}` | Per-service pod metadata. |
| `extraVolumes` / `extraVolumeMounts` | list | `[]` | Per-service extra volumes. |
| `service.type` | enum | `ClusterIP` | Service type. |
| `service.annotations` / `labels` | map | `{}` | Service metadata. |

A `null` value in a per-service block means **"inherit from the
profile/global default"**. This is what lets a profile set a storage class
once and have every service pick it up, while a single service can still
override it.

---

## 5. How the profile merge works

`templates/_helpers.tpl` defines `ngsh.deepMerge`, which merges the active
profile overlay onto the base values, and `ngsh.effectiveValues`, which
performs that merge and adds the chart/release metadata.

The merge is **not** sprig's `mergeOverwrite`. That function skips empty
source values, so an overlay of `ingress.enabled: false` would be ignored over
a base of `true` — a profile would be unable to turn a feature off.
`ngsh.deepMerge` recurses explicitly and lets the overlay win in every case,
including an explicit `false`, `0`, or an empty list.

`ngsh.svcPersistence`, `ngsh.svcAutoscaling` and `ngsh.svcPodDisruptionBudget`
then resolve the `null` inheritance for a single service.

---

## 6. Environment contract

Every container receives these variables, whatever the profile:

| Variable | Source |
|---|---|
| `NGSH_SERVICE_NAME` | `services.<name>.name` |
| `PORT`, `NGSH_PORT` | `services.<name>.port` |
| `NGSH_HOST` | `0.0.0.0` |
| `NGSH_ENVIRONMENT` | `global.environment` |
| `NGSH_DEPLOYMENT_PROFILE` | the active profile |
| `NGSH_DEPLOYMENT_ZONE` | `global.zone` |
| `NGSH_IDENTITY_PROVIDER` | `config.identityProvider` |
| `NGSH_CLASSIFICATION_LEVEL` | `config.classificationLevel` |
| `NGSH_TENANT` | `config.tenant` |
| `NGSH_LOG_LEVEL`, `NGSH_LOG_FORMAT` | `config.logLevel`, `config.logFormat` |
| `NGSH_GRAPH_BACKEND`, `NGSH_GRAPH_NAMESPACE` | `config.graphBackend`, `config.graphNamespace` |
| `NGSH_CONFIG_FILE` | `/etc/ngsh/ngsh-config.json` (the mounted ConfigMap) |
| `OTEL_SERVICE_NAME` | `services.<name>.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `_PROTOCOL` / `_TLS_INSECURE` | `config.otel.*` |
| `OTEL_RESOURCE_ATTRIBUTES` | Built from the profile, zone, classification and tenant |
| `DATABASE_URL`, `NGSH_DSN` | From the Secret — the same value under both names, because the platform's configuration layer reads the first of the two that is set |
| `NGSH_<KEY>_URL` | One per entry in `services.<name>.upstreams` |
| `NGSH_DATA_DIR` | Present when the service has persistence |
| `NGSH_WL_TOKEN_FILE`, `NGSH_WL_AUDIENCE` | Present when workload identity is enabled |

> The console receives an `NGSH_<KEY>_URL` variable for every platform
> service. The console image shipped for Compose hard-codes the Compose
> service names in its nginx configuration; the image deployed in Kubernetes
> is expected to **template** its nginx configuration from these variables
> (the upstream nginx image substitutes `/etc/nginx/templates/*.template`).
> This is the one place where the two topologies differ, and it is a
> property of the console image, not of this chart.

---

## 7. Secrets

`values.secrets` holds **placeholders only**. The defaults read
`CHANGE_ME_not_a_real_password` and friends. Rendering a release from them
means the release is not promotable outside a local environment, and
`NOTES.txt` says so on every install.

In an accredited zone:

```bash
helm upgrade --install ngsh deploy/helm/ngsh \
  --namespace ngsh \
  --set deploymentProfiles.activeProfile=il5 \
  --set existingSecret=ngsh-prod-secret
```

With `existingSecret` set, the chart renders **no** Secret at all and
references the supplied one. The expected keys are:

```
POSTGRES_USER
POSTGRES_PASSWORD
DATABASE_URL
JWT_SIGNING_KEY
OIDC_CLIENT_SECRET
FABRIC_SIGNING_KEY
```

`DATABASE_URL` is assembled by the chart from the individual fields when the
chart renders its own Secret. When you supply your own Secret, you must
include a complete `DATABASE_URL` key. Percent-encode any password character
that is reserved in a URI.

The scheme is **`postgresql://`**, not `postgres://`: the platform's SQL driver
accepts only the long form. The chart uses the long form.

> The chart always points the services at PostgreSQL, because that is the
> platform's target relational store in every accredited zone. The platform's
> current `ngsh-core` release implements only the SQLite executor and raises
> `NotImplementedError` for a PostgreSQL DSN; that executor lands in a later
> increment. Until then, the **local** Compose topology is the one that runs
> end to end (see `deploy/compose/README.md`, §6), and this chart's PostgreSQL
> wiring is verified but not yet exercised by a running service.

---

## 8. Verify a release

```bash
# Run the health test
helm test ngsh --namespace ngsh --logs

# Every pod ready?
kubectl get pods -n ngsh -l app.kubernetes.io/part-of=ngsh

# Which profile is live?
kubectl get deployments -n ngsh -o custom-columns=\
NAME:.metadata.name,PROFILE:.metadata.labels.ngsh\\.io/deployment-profile

# What is the fabric's host networking?
kubectl get deployment ngsh-fabric -n ngsh -o jsonpath=\
'{.spec.template.spec.hostNetwork}'

# The projected workload-identity token
kubectl exec -n ngsh deploy/ngsh-fabric -- ls -l /var/run/secrets/ngsh
```

---

## 9. Linting

```bash
helm lint deploy/helm/ngsh --set deploymentProfiles.activeProfile=il6
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=il6 | kubectl apply --dry-run=client -f -
```

`values.schema.json` is validated by Helm on every `install`, `upgrade`,
`lint` and `template`, so a malformed values file is rejected before
anything is rendered.
