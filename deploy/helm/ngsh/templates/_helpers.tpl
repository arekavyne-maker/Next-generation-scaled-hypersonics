{{/*
================================================================================
NGSH Helm helpers
================================================================================
Naming, labelling, and the deployment-profile merge.

All helpers that need the effective (profile-merged) values take the effective
values map as their context, i.e. `include "ngsh.labels" $v` where
`$v := include "ngsh.effectiveValues" . | fromYaml`.
================================================================================
*/}}

{{/*
--------------------------------------------------------------------------------
ngsh.deepMerge — merge an overlay onto a base map.

Sprig's mergeOverwrite cannot express "turn this off": it skips empty source
values, so an overlay `ingress.enabled: false` would be ignored over a base of
`true`. A deployment profile has to be able to turn features off as well as on,
so this helper recurses explicitly and lets the overlay win in every case,
including explicit false, 0 and empty lists.

Usage: include "ngsh.deepMerge" (dict "base" $base "over" $overlay)
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.deepMerge" -}}
{{- $base := .base | deepCopy -}}
{{- $over := .over | default (dict) -}}
{{- range $k, $v := $over -}}
{{- if and (kindIs "map" $v) (hasKey $base $k) (kindIs "map" (index $base $k)) -}}
{{- $merged := include "ngsh.deepMerge" (dict "base" (index $base $k) "over" $v) | fromYaml -}}
{{- $_ := set $base $k $merged -}}
{{- else -}}
{{- $_ := set $base $k $v -}}
{{- end -}}
{{- end -}}
{{- toYaml $base -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
ngsh.effectiveValues — the base values merged with the active profile overlay.

The result also carries the chart and release metadata, so that every template
works from a single map and never has to mix .Values with chart context.

Usage: $v := include "ngsh.effectiveValues" . | fromYaml
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.effectiveValues" -}}
{{- $base := deepCopy (omit .Values "deploymentProfiles") -}}
{{- $active := .Values.deploymentProfiles.activeProfile | default "local" -}}
{{- $profiles := .Values.deploymentProfiles.profiles | default (dict) -}}
{{- $overlay := index $profiles $active | default (dict) -}}
{{- $merged := include "ngsh.deepMerge" (dict "base" $base "over" $overlay) | fromYaml -}}
{{- $_ := set $merged "activeProfile" $active -}}
{{- $_ := set $merged "chartName" .Chart.Name -}}
{{- $_ := set $merged "chartVersion" .Chart.Version -}}
{{- $_ := set $merged "appVersion" .Chart.AppVersion -}}
{{- $_ := set $merged "releaseName" .Release.Name -}}
{{- $_ := set $merged "releaseNamespace" .Release.Namespace -}}
{{- $_ := set $merged "releaseService" .Release.Service -}}
{{- $_ := set $merged "isHelmTest" (eq .Release.Service "HelmTest") -}}
{{- toYaml $merged -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Names
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.name" -}}
{{- default .chartName .nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ngsh.fullname" -}}
{{- if .fullnameOverride -}}
{{- .fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .chartName .nameOverride -}}
{{- if contains $name .releaseName -}}
{{- .releaseName | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .releaseName $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Per-service object name: <fullname>-<service key>. */}}
{{- define "ngsh.serviceObjectName" -}}
{{- printf "%s-%s" (include "ngsh.fullname" .ctx) .key | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* In-cluster DNS name of a service. */}}
{{- define "ngsh.serviceDNSName" -}}
{{- printf "%s-%s" (include "ngsh.fullname" .ctx) .svc.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ngsh.chart" -}}
{{- printf "%s-%s" .chartName (.chartVersion | toString | replace "+" "_") | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ngsh.configMapName" -}}
{{- printf "%s-config" (include "ngsh.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ngsh.secretName" -}}
{{- if .existingSecret -}}
{{- .existingSecret | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-secret" (include "ngsh.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Labels and annotations
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.labels" -}}
helm.sh/chart: {{ include "ngsh.chart" . }}
app.kubernetes.io/name: {{ include "ngsh.name" . | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/instance: {{ .releaseName | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/version: {{ .appVersion | quote }}
app.kubernetes.io/part-of: ngsh
app.kubernetes.io/managed-by: {{ .releaseService }}
ngsh.io/deployment-profile: {{ .activeProfile }}
{{- with .global.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* Selector labels. Immutable for the life of a Deployment. */}}
{{- define "ngsh.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ngsh.name" . | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/instance: {{ .releaseName | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "ngsh.commonAnnotations" -}}
{{- with .global.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Service accounts
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.serviceAccountName" -}}
{{- if .serviceAccount.create -}}
{{- default (include "ngsh.fullname" .) .serviceAccount.name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- default "default" .serviceAccount.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
The service account the pods run as. When workload identity is enabled the
pods use the dedicated workload-identity service account instead, because that
is the account whose audience-scoped token is minted.
*/}}
{{- define "ngsh.podServiceAccountName" -}}
{{- if .serviceAccount.workloadIdentity.enabled -}}
{{- printf "%s-workload-identity" (include "ngsh.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "ngsh.serviceAccountName" . -}}
{{- end -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Images
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.image" -}}
{{- $v := .v -}}
{{- $svc := .svc -}}
{{- $registry := $svc.image.registry | default $v.global.imageRegistry -}}
{{- $tag := $svc.image.tag | default $v.appVersion | toString -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry $svc.image.repository $tag -}}
{{- else -}}
{{- printf "%s:%s" $svc.image.repository $tag -}}
{{- end -}}
{{- end -}}

{{- define "ngsh.imagePullPolicy" -}}
{{- $v := .v -}}
{{- $svc := .svc -}}
{{- $svc.image.pullPolicy | default $v.global.imagePullPolicy -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Per-service resolved settings

Per-service values use null to mean "inherit from the global/profile default".
The helpers below resolve the inheritance once so the templates stay readable.
--------------------------------------------------------------------------------
*/}}

{{/* Persistence: resolved storage settings for one service. */}}
{{- define "ngsh.svcPersistence" -}}
{{- $v := .v -}}
{{- $p := .svc.persistence | default (dict) -}}
{{- $g := $v.persistence -}}
{{- $out := dict
      "enabled" $g.enabled
      "size" $g.size
      "storageClass" $g.storageClass
      "accessModes" $g.accessModes
      "existingClaim" $g.existingClaim
      "mountPath" $g.mountPath -}}
{{- if not (kindIs "invalid" $p.enabled) -}}{{- $_ := set $out "enabled" $p.enabled -}}{{- end -}}
{{- if not (kindIs "invalid" $p.size) -}}{{- $_ := set $out "size" $p.size -}}{{- end -}}
{{- if not (kindIs "invalid" $p.storageClass) -}}{{- $_ := set $out "storageClass" $p.storageClass -}}{{- end -}}
{{- if not (kindIs "invalid" $p.accessModes) -}}{{- $_ := set $out "accessModes" $p.accessModes -}}{{- end -}}
{{- if not (kindIs "invalid" $p.existingClaim) -}}{{- $_ := set $out "existingClaim" $p.existingClaim -}}{{- end -}}
{{- if not (kindIs "invalid" $p.mountPath) -}}{{- $_ := set $out "mountPath" $p.mountPath -}}{{- end -}}
{{- toYaml $out -}}
{{- end -}}

{{/* Autoscaling: resolved HPA settings for one service. */}}
{{- define "ngsh.svcAutoscaling" -}}
{{- $v := .v -}}
{{- $a := .svc.autoscaling | default (dict) -}}
{{- $g := $v.autoscaling -}}
{{- $out := dict
      "enabled" $g.enabled
      "minReplicas" $g.minReplicas
      "maxReplicas" $g.maxReplicas
      "targetCPUUtilizationPercentage" $g.targetCPUUtilizationPercentage
      "targetMemoryUtilizationPercentage" $g.targetMemoryUtilizationPercentage
      "annotations" $g.annotations
      "behavior" $g.behavior -}}
{{- if not (kindIs "invalid" $a.enabled) -}}{{- $_ := set $out "enabled" $a.enabled -}}{{- end -}}
{{- if not (kindIs "invalid" $a.minReplicas) -}}{{- $_ := set $out "minReplicas" $a.minReplicas -}}{{- end -}}
{{- if not (kindIs "invalid" $a.maxReplicas) -}}{{- $_ := set $out "maxReplicas" $a.maxReplicas -}}{{- end -}}
{{- if not (kindIs "invalid" $a.targetCPUUtilizationPercentage) -}}{{- $_ := set $out "targetCPUUtilizationPercentage" $a.targetCPUUtilizationPercentage -}}{{- end -}}
{{- if not (kindIs "invalid" $a.targetMemoryUtilizationPercentage) -}}{{- $_ := set $out "targetMemoryUtilizationPercentage" $a.targetMemoryUtilizationPercentage -}}{{- end -}}
{{- toYaml $out -}}
{{- end -}}

{{/* PodDisruptionBudget: resolved PDB settings for one service. */}}
{{- define "ngsh.svcPodDisruptionBudget" -}}
{{- $v := .v -}}
{{- $d := .svc.podDisruptionBudget | default (dict) -}}
{{- $g := $v.podDisruptionBudget -}}
{{- $out := dict
      "enabled" $g.enabled
      "minAvailable" $g.minAvailable
      "maxUnavailable" $g.maxUnavailable
      "annotations" $g.annotations -}}
{{- if not (kindIs "invalid" $d.enabled) -}}{{- $_ := set $out "enabled" $d.enabled -}}{{- end -}}
{{- if not (kindIs "invalid" $d.minAvailable) -}}{{- $_ := set $out "minAvailable" $d.minAvailable -}}{{- end -}}
{{- if not (kindIs "invalid" $d.maxUnavailable) -}}{{- $_ := set $out "maxUnavailable" $d.maxUnavailable -}}{{- end -}}
{{- toYaml $out -}}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
Probes
--------------------------------------------------------------------------------
httpGet against the named container port "http". The image contract is that
GET /healthz and GET /readyz return 200 with a JSON body.
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.probe" -}}
{{- $probe := .probe -}}
httpGet:
  path: {{ $probe.path | quote }}
  port: http
  scheme: HTTP
initialDelaySeconds: {{ $probe.initialDelaySeconds }}
periodSeconds: {{ $probe.periodSeconds }}
timeoutSeconds: {{ $probe.timeoutSeconds }}
failureThreshold: {{ $probe.failureThreshold }}
{{- end -}}

{{/*
--------------------------------------------------------------------------------
OTel resource attributes, built from the effective values.
--------------------------------------------------------------------------------
*/}}
{{- define "ngsh.otelResourceAttributes" -}}
{{- $v := .v -}}
{{- $svc := .svc -}}
{{- $attrs := list
      (printf "service.namespace=ngsh")
      (printf "service.version=%s" $v.appVersion)
      (printf "deployment.profile=%s" $v.activeProfile)
      (printf "deployment.zone.name=%s" $v.global.zone)
      (printf "ngsh.classification.level=%s" $v.config.classificationLevel)
      (printf "ngsh.tenant=%s" $v.config.tenant) -}}
{{- range $k, $val := $v.config.otel.resourceAttributes -}}
{{- $attrs = append $attrs (printf "%s=%s" $k $val) -}}
{{- end -}}
{{- join "," $attrs -}}
{{- end -}}
