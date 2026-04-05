{{/*
signoz-dashboards.configmaps generates ConfigMaps for each enabled dashboard.
The dashboard sidecar watches for the signoz.io/dashboard=true label and syncs
them to SigNoz automatically.

Usage (in a consuming chart's template):
  {{- include "signoz-dashboards.configmaps" (dict "root" . "dashboards" .Values.dashboards) }}

Dashboard JSON files must live in the consuming chart's dashboards/ directory,
named <key>.json to match the dashboards map key.

Required values (per dashboard entry):
  enabled: true/false
  name: "Human Readable Dashboard Name"

Optional values:
  tags: "tag1,tag2"
*/}}
{{- define "signoz-dashboards.configmaps" -}}
{{- $root := .root -}}
{{- range $key, $config := .dashboards }}
{{- if $config.enabled }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $root.Release.Name }}-dashboard-{{ $key }}
  namespace: {{ $root.Release.Namespace }}
  labels:
    app.kubernetes.io/managed-by: {{ $root.Release.Service }}
    signoz.io/dashboard: "true"
  annotations:
    signoz.io/dashboard-name: {{ $config.name | quote }}
    {{- if $config.tags }}
    signoz.io/dashboard-tags: {{ $config.tags | quote }}
    {{- end }}
data:
  dashboard.json: |-
    {{- $root.Files.Get (printf "dashboards/%s.json" $key) | nindent 4 }}
{{- end }}
{{- end }}
{{- end }}
